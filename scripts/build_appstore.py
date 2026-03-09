#!/usr/bin/env python3
"""
Build script for ZimaOS AppStore online metadata.

Processes Apps/ directory to produce a GitHub Pages-ready static site:
  - Generates store.json from store-config.json
  - Splits docker-compose.yml into pure compose + meta.json
  - Generates global index.json with categories and content hashes
  - Copies image assets
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("Warning: Pillow not installed. Image optimization disabled.", file=sys.stderr)


# Fields to keep in docker-compose.yml x-casaos block (runtime essentials)
COMPOSE_KEEP_FIELDS = {"main", "index", "port_map", "scheme", "icon", "title"}

# Image file extensions to copy
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

# Image optimization settings
MAX_IMAGE_WIDTH = 1280
WEBP_QUALITY = 85

# Store config input filename
STORE_CONFIG_FILE = "store-config.json"

# Category list input filename (optional, for official store)
CATEGORY_LIST_FILE = "category-list.json"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build ZimaOS AppStore online metadata"
    )
    parser.add_argument(
        "--source",
        default=".",
        help="Source repository root (default: current directory)",
    )
    parser.add_argument(
        "--output",
        default="dist",
        help="Output directory (default: dist)",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Base URL prefix for resource links in index.json (e.g. https://user.github.io/repo)",
    )
    return parser.parse_args()


def content_hash(*parts):
    """Compute a short SHA-256 hash over multiple content strings/bytes."""
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, str):
            p = p.encode("utf-8")
        h.update(p)
    return h.hexdigest()[:8]


def url_join(base, path):
    """Join base URL and path, handling trailing slashes."""
    if not base:
        return path
    return f"{base.rstrip('/')}/{path}"


def normalize_locale_key(key):
    """Normalize locale key to ll_CC format (e.g. en_us -> en_US, zh_cn -> zh_CN)."""
    parts = key.split("_", 1)
    if len(parts) == 2:
        return f"{parts[0].lower()}_{parts[1].upper()}"
    return key


def normalize_locale_dict(d):
    """Recursively normalize all locale keys in i18n dicts."""
    if not isinstance(d, dict):
        return d
    return {normalize_locale_key(k): v for k, v in d.items()}


# Fields in x-casaos that contain i18n locale dicts
I18N_FIELDS = {"title", "tagline", "description"}
# Fields that contain nested i18n dicts (e.g. tips.before_install)
I18N_NESTED_FIELDS = {"tips"}


def normalize_i18n_in_dict(data):
    """Normalize locale keys for all known i18n fields in a dict."""
    for field in I18N_FIELDS:
        if field in data and isinstance(data[field], dict):
            data[field] = normalize_locale_dict(data[field])
    for field in I18N_NESTED_FIELDS:
        if field in data and isinstance(data[field], dict):
            for sub_key, sub_val in data[field].items():
                if isinstance(sub_val, dict):
                    data[field][sub_key] = normalize_locale_dict(sub_val)
    return data


def to_json_safe(obj):
    """Recursively convert Python objects to JSON-serializable values."""
    if isinstance(obj, datetime):
        # Keep timezone information when present.
        return obj.isoformat()
    if isinstance(obj, date):
        # YAML unquoted dates (e.g. 2024-06-01) are parsed as date.
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_safe(v) for v in obj]
    return obj


def extract_image_filenames(app_dir):
    """Return a dict of image type -> filename for images that exist."""
    images = {}
    for f in app_dir.iterdir():
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
            images[f.name] = f.name
    return images


def optimize_and_convert_image(src_path, dst_path, max_width=MAX_IMAGE_WIDTH, quality=WEBP_QUALITY):
    """
    Optimize and convert image to WebP format.
    - Converts PNG/JPG to WebP
    - Resizes if width > max_width (maintaining aspect ratio)
    - Skips SVG files (copies as-is)

    Returns the output filename (with .webp extension if converted).
    """
    if not PILLOW_AVAILABLE:
        # Fallback: just copy the file
        shutil.copy2(src_path, dst_path)
        return dst_path.name

    src_ext = src_path.suffix.lower()

    # Skip SVG files - copy as-is
    if src_ext == '.svg':
        shutil.copy2(src_path, dst_path)
        return dst_path.name

    # Skip if already WebP and doesn't need resizing
    if src_ext == '.webp':
        try:
            with Image.open(src_path) as img:
                if img.width <= max_width:
                    shutil.copy2(src_path, dst_path)
                    return dst_path.name
        except Exception:
            shutil.copy2(src_path, dst_path)
            return dst_path.name

    try:
        with Image.open(src_path) as img:
            # Convert RGBA to RGB for WebP (if needed)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Resize if needed
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

            # Convert to WebP
            webp_path = dst_path.with_suffix('.webp')
            img.save(webp_path, 'WEBP', quality=quality, method=6)

            return webp_path.name

    except Exception as e:
        print(f"    WARN: Failed to optimize {src_path.name}: {e}", file=sys.stderr)
        # Fallback: copy original
        shutil.copy2(src_path, dst_path)
        return dst_path.name


def convert_svg_icon_to_png(src_svg, dst_png):
    """
    Convert icon.svg to icon.png using rsvg-convert.
    Returns output filename on success, or None on failure.
    """
    try:
        subprocess.run(
            ["rsvg-convert", str(src_svg), "-o", str(dst_png)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        return dst_png.name
    except FileNotFoundError:
        print("    WARN: rsvg-convert not found, cannot convert icon.svg to icon.png", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip()
        print(f"    WARN: Failed to convert {src_svg.name} -> {dst_png.name}: {err}", file=sys.stderr)
    return None


def resolve_app_id(compose_data, xcasaos, dir_name):
    """Determine the canonical app ID."""
    # Priority: store_app_id > compose name > directory name lowered
    if xcasaos.get("store_app_id"):
        return xcasaos["store_app_id"]
    if compose_data.get("name"):
        return compose_data["name"]
    return dir_name.lower()


def load_store_config(source):
    """Load store-config.json and return store.json content."""
    config_path = source / STORE_CONFIG_FILE
    if not config_path.exists():
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Normalize i18n fields
    for field in ("name", "description"):
        if field in config and isinstance(config[field], dict):
            config[field] = normalize_locale_dict(config[field])

    return config


def load_categories(source, entries):
    """
    Load categories from category-list.json if it exists (official store),
    otherwise auto-extract unique category names from app entries.
    """
    cat_path = source / CATEGORY_LIST_FILE
    if cat_path.exists():
        with open(cat_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Auto-extract: collect unique non-empty category names from entries
    seen = set()
    categories = []
    for entry in entries:
        cat = entry.get("category", "")
        if cat and cat not in seen:
            seen.add(cat)
            categories.append({"name": cat})
    return categories


def split_compose(compose_data):
    """
    Split a parsed docker-compose.yml into:
      - clean compose dict (with minimal x-casaos)
      - meta dict (remaining x-casaos fields)

    Modifies compose_data in place and returns (compose_data, meta_dict).
    """
    xcasaos = compose_data.pop("x-casaos", {})

    # Coerce port_map to string (YAML parses unquoted 8080 as int)
    if "port_map" in xcasaos and not isinstance(xcasaos["port_map"], str):
        xcasaos["port_map"] = str(xcasaos["port_map"])

    # Partition x-casaos fields
    compose_xcasaos = {}
    meta = {}
    for key, value in xcasaos.items():
        if key in COMPOSE_KEEP_FIELDS:
            compose_xcasaos[key] = value
        else:
            meta[key] = value

    # Remove service-level x-casaos blocks
    services = compose_data.get("services", {})
    if isinstance(services, dict):
        for svc_name, svc_def in services.items():
            if isinstance(svc_def, dict) and "x-casaos" in svc_def:
                del svc_def["x-casaos"]

    # Put back minimal x-casaos
    compose_data["x-casaos"] = compose_xcasaos

    return compose_data, meta, xcasaos


def process_app(app_dir, output_root, base_url):
    """
    Process a single app directory.

    Flow: parse compose → convert images → write meta.json → build index entry.
    Returns an index entry dict, or None if skipped.
    """
    compose_path = app_dir / "docker-compose.yml"
    if not compose_path.exists():
        compose_path = app_dir / "docker-compose.yaml"
    if not compose_path.exists():
        return None

    with open(compose_path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    try:
        compose_data = yaml.safe_load(raw_content)
    except yaml.YAMLError as e:
        print(f"  YAML ERROR: {app_dir.name}: {e}", file=sys.stderr)
        return None

    if not compose_data or not isinstance(compose_data, dict):
        return None
    if "x-casaos" not in compose_data:
        return None

    # Get original x-casaos before splitting
    original_xcasaos = dict(compose_data.get("x-casaos", {}))

    # Resolve app ID
    app_id = resolve_app_id(compose_data, original_xcasaos, app_dir.name)

    # Split compose and metadata
    compose_data, meta, _ = split_compose(compose_data)

    # Normalize i18n locale keys (en_us -> en_US, zh_cn -> zh_CN, etc.)
    normalize_i18n_in_dict(compose_data.get("x-casaos", {}))
    normalize_i18n_in_dict(meta)
    normalize_i18n_in_dict(original_xcasaos)

    # Create output directory
    app_output = output_root / "apps" / app_id
    app_output.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Convert and copy all image files ──
    copied_images = []
    image_mapping = {}  # original_name -> output_name
    has_icon_svg = (app_dir / "icon.svg").exists()
    for img_file in app_dir.iterdir():
        if not img_file.is_file() or img_file.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        dst_path = app_output / img_file.name

        if img_file.stem.lower() == "icon":
            # Icon strategy:
            # - If icon.svg exists, keep SVG + generate PNG fallback, skip other icon formats.
            # - Otherwise keep original icon file as-is.
            if has_icon_svg:
                if img_file.suffix.lower() == ".svg":
                    shutil.copy2(img_file, app_output / "icon.svg")
                    copied_images.append("icon.svg")
                    image_mapping["icon.svg"] = "icon.svg"

                    png_name = convert_svg_icon_to_png(img_file, app_output / "icon.png")
                    if png_name:
                        copied_images.append(png_name)
                        image_mapping["icon.png"] = png_name
                # Ignore icon.png/icon.jpg/etc. when icon.svg is present.
                continue
            else:
                shutil.copy2(img_file, dst_path)
                copied_images.append(img_file.name)
                image_mapping[img_file.name] = img_file.name
        else:
            output_name = optimize_and_convert_image(img_file, dst_path)
            copied_images.append(output_name)
            image_mapping[img_file.name] = output_name

    # ── Step 2: Resolve asset URLs ──
    app_path = f"apps/{app_id}"

    # Icon priority: SVG > PNG > JPG > WebP
    icon_filename = "icon.png"  # default fallback
    if "icon.svg" in copied_images:
        icon_filename = "icon.svg"
    elif "icon.png" in image_mapping:
        icon_filename = image_mapping["icon.png"]
    elif "icon.jpg" in image_mapping:
        icon_filename = image_mapping["icon.jpg"]
    elif "icon.webp" in copied_images:
        icon_filename = "icon.webp"

    icon_url = url_join(base_url, f"{app_path}/{icon_filename}")

    def _resolve_asset_filename(url_or_name):
        """Extract filename from URL, map to converted output name."""
        if not url_or_name:
            return None
        fname = url_or_name.rsplit("/", 1)[-1] if "/" in str(url_or_name) else str(url_or_name)
        if fname in image_mapping:
            return image_mapping[fname]
        webp_name = f"{Path(fname).stem}.webp"
        if webp_name in copied_images:
            return webp_name
        return fname

    # ── Step 3: Update compose x-casaos.icon to point to built output ──
    compose_data["x-casaos"]["icon"] = icon_url

    # Write clean docker-compose.yml (after icon URL is updated)
    compose_content = yaml.dump(
        compose_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    (app_output / "docker-compose.yml").write_text(compose_content, encoding="utf-8")

    # ── Step 4: Build meta.json with full URLs ──
    if "icon" in meta:
        del meta["icon"]  # icon stays in compose

    if "thumbnail" in meta:
        thumb_fname = _resolve_asset_filename(meta["thumbnail"])
        meta["thumbnail"] = url_join(base_url, f"{app_path}/{thumb_fname}") if thumb_fname else ""

    if "screenshot_link" in meta:
        raw = meta["screenshot_link"]
        if raw and isinstance(raw, list):
            updated = []
            for url in raw:
                fname = _resolve_asset_filename(url)
                if fname:
                    updated.append(url_join(base_url, f"{app_path}/{fname}"))
            meta["screenshot_link"] = updated
        else:
            meta["screenshot_link"] = []

    # Write meta.json (single write, after image conversion)
    meta_content = json.dumps(to_json_safe(meta), ensure_ascii=False, indent=2)
    (app_output / "meta.json").write_text(meta_content, encoding="utf-8")

    # ── Step 5: Build index entry ──
    chash = content_hash(compose_content, meta_content)

    # Thumbnail URL from meta (already a full URL now)
    thumbnail_url = meta.get("thumbnail", "")

    entry = {
        "id": app_id,
        "title": original_xcasaos.get("title", {}),
        "tagline": original_xcasaos.get("tagline", {}),
        "category": original_xcasaos.get("category", ""),
        "author": original_xcasaos.get("author", ""),
        "developer": original_xcasaos.get("developer", ""),
        "architectures": original_xcasaos.get("architectures", []),
        "icon": icon_url,
        "thumbnail": thumbnail_url,
        "compose_url": url_join(base_url, f"{app_path}/docker-compose.yml"),
        "meta_url": url_join(base_url, f"{app_path}/meta.json"),
        "content_hash": chash,
    }

    return entry


def main():
    args = parse_args()
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()

    print(f"Source: {source}")
    print(f"Output: {output}")
    print(f"Base URL: {args.base_url or '(relative)'}")
    print()

    # Clean output directory
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    apps_dir = source / "Apps"
    if not apps_dir.exists():
        print(f"Error: Apps directory not found at {apps_dir}", file=sys.stderr)
        sys.exit(1)

    # Generate store.json from store-config.json
    store_config = load_store_config(source)
    if store_config:
        store_json_path = output / "store.json"
        store_json_path.write_text(
            json.dumps(to_json_safe(store_config), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  STORE {store_config.get('store_id', '(unknown)')}")
    else:
        print(f"  WARN  {STORE_CONFIG_FILE} not found, skipping store.json")

    # Process all apps
    entries = []
    skipped = []

    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue

        entry = process_app(app_dir, output, args.base_url)
        if entry:
            entries.append(entry)
            print(f"  OK   {entry['id']}")
        else:
            skipped.append(app_dir.name)
            print(f"  SKIP {app_dir.name}")

    # Sort entries by ID for stable output
    entries.sort(key=lambda e: e["id"])

    # Load categories
    categories = load_categories(source, entries)

    # Build global index.json
    index = {
        "version": 2,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "categories": categories,
        "app_count": len(entries),
        "apps": entries,
    }

    index_path = output / "index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Summary
    print(f"\n{'='*50}")
    print(f"Done! {len(entries)} apps processed, {len(skipped)} skipped")
    print(f"Output: {output}/")
    if store_config:
        print(f"  store.json  (store_id: {store_config.get('store_id', '?')})")
    print(f"  index.json  ({index_path.stat().st_size / 1024:.1f} KB)")
    print(f"  categories  ({len(categories)})")
    if skipped:
        print(f"  Skipped: {', '.join(skipped)}")


if __name__ == "__main__":
    main()

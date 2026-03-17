#!/usr/bin/env python3
"""
Build script for ZimaOS AppStore online metadata.

Processes Apps/ directory to produce a GitHub Pages-ready static site
with per-language output directories:

  dist/
    assets/apps/{app_id}/          # shared images (once)
    {locale}/store.json            # single-language store info
    {locale}/index.json            # single-language app listing
    {locale}/apps/{app_id}/
        docker-compose.yml         # single-language compose
        meta.json                  # single-language metadata
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

# Supported languages config filename
SUPPORTED_LANGUAGES_FILE = "supported-languages.json"

# Default / fallback locale
DEFAULT_LOCALE = "en_US"


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
        help="Base URL prefix for resource links (e.g. https://user.github.io/repo)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def content_hash(*parts):
    """Compute a short SHA-256 hash over multiple content strings/bytes."""
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, str):
            p = p.encode("utf-8")
        h.update(p)
    return h.hexdigest()[:8]


def normalize_base_url(base):
    """Ensure base URL ends with '/' for simple concatenation."""
    if not base:
        return ""
    return base.rstrip("/") + "/"


def url_join(base, path):
    """Join base URL and path, handling trailing slashes."""
    if not base:
        return path
    return f"{base.rstrip('/')}/{path}"


def normalize_locale_key(key):
    """Normalize locale key to ll_CC format (e.g. en_us -> en_US)."""
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
I18N_FIELDS = {"title", "tagline", "description", "releaseNotes"}
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


def resolve_i18n(value, locale):
    """Resolve an i18n dict to a plain string for the given locale.

    Falls back to DEFAULT_LOCALE, then first available value.
    If value is already a string, return as-is.
    """
    if not isinstance(value, dict):
        return value if value is not None else ""
    if locale in value:
        return value[locale]
    if DEFAULT_LOCALE in value:
        return value[DEFAULT_LOCALE]
    # Last resort: first available value
    return next(iter(value.values()), "")


def resolve_i18n_nested(value, locale):
    """Resolve a nested i18n structure (like tips) for a given locale."""
    if not isinstance(value, dict):
        return value
    result = {}
    for key, sub_val in value.items():
        result[key] = resolve_i18n(sub_val, locale)
    return result


def to_json_safe(obj):
    """Recursively convert Python objects to JSON-serializable values."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_safe(v) for v in obj]
    return obj


def load_supported_languages(source):
    """Load supported languages list from config file."""
    lang_path = source / SUPPORTED_LANGUAGES_FILE
    if not lang_path.exists():
        print(f"  WARN  {SUPPORTED_LANGUAGES_FILE} not found, using {DEFAULT_LOCALE} only",
              file=sys.stderr)
        return [DEFAULT_LOCALE]
    with open(lang_path, "r", encoding="utf-8") as f:
        languages = json.load(f)
    # Ensure default locale is always included
    if DEFAULT_LOCALE not in languages:
        languages.insert(0, DEFAULT_LOCALE)
    return languages


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------

def optimize_and_convert_image(src_path, dst_path, max_width=MAX_IMAGE_WIDTH, quality=WEBP_QUALITY):
    """Optimize and convert image to WebP format. Returns output filename."""
    if not PILLOW_AVAILABLE:
        shutil.copy2(src_path, dst_path)
        return dst_path.name

    src_ext = src_path.suffix.lower()

    if src_ext == '.svg':
        shutil.copy2(src_path, dst_path)
        return dst_path.name

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
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

            webp_path = dst_path.with_suffix('.webp')
            img.save(webp_path, 'WEBP', quality=quality, method=6)
            return webp_path.name

    except Exception as e:
        print(f"    WARN: Failed to optimize {src_path.name}: {e}", file=sys.stderr)
        shutil.copy2(src_path, dst_path)
        return dst_path.name


def convert_svg_icon_to_png(src_svg, dst_png):
    """Convert icon.svg to icon.png using rsvg-convert."""
    try:
        subprocess.run(
            ["rsvg-convert", str(src_svg), "-o", str(dst_png)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        return dst_png.name
    except FileNotFoundError:
        print("    WARN: rsvg-convert not found, cannot convert icon.svg to icon.png", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip()
        print(f"    WARN: Failed to convert {src_svg.name} -> {dst_png.name}: {err}", file=sys.stderr)
    return None


def process_app_assets(app_dir, assets_output):
    """Process images for a single app into the shared assets directory.

    Returns (copied_images, image_mapping, icon_filename).
    """
    assets_output.mkdir(parents=True, exist_ok=True)

    copied_images = []
    image_mapping = {}  # original_name -> output_name
    has_icon_svg = (app_dir / "icon.svg").exists()

    for img_file in app_dir.iterdir():
        if not img_file.is_file() or img_file.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        dst_path = assets_output / img_file.name

        if img_file.stem.lower() == "icon":
            if has_icon_svg:
                if img_file.suffix.lower() == ".svg":
                    shutil.copy2(img_file, assets_output / "icon.svg")
                    copied_images.append("icon.svg")
                    image_mapping["icon.svg"] = "icon.svg"
                    png_name = convert_svg_icon_to_png(img_file, assets_output / "icon.png")
                    if png_name:
                        copied_images.append(png_name)
                        image_mapping["icon.png"] = png_name
                continue
            else:
                shutil.copy2(img_file, dst_path)
                copied_images.append(img_file.name)
                image_mapping[img_file.name] = img_file.name
        else:
            output_name = optimize_and_convert_image(img_file, dst_path)
            copied_images.append(output_name)
            image_mapping[img_file.name] = output_name

    # Determine icon filename
    icon_filename = "icon.png"
    if "icon.svg" in copied_images:
        icon_filename = "icon.svg"
    elif "icon.png" in image_mapping:
        icon_filename = image_mapping["icon.png"]
    elif "icon.jpg" in image_mapping:
        icon_filename = image_mapping["icon.jpg"]
    elif "icon.webp" in copied_images:
        icon_filename = "icon.webp"

    return copied_images, image_mapping, icon_filename


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------

def resolve_app_id(compose_data, xcasaos, dir_name):
    """Determine the canonical app ID."""
    if xcasaos.get("store_app_id"):
        return xcasaos["store_app_id"]
    if compose_data.get("name"):
        return compose_data["name"]
    return dir_name.lower()


def load_store_config(source):
    """Load store-config.json and return store config dict."""
    config_path = source / STORE_CONFIG_FILE
    if not config_path.exists():
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    for field in ("name", "description"):
        if field in config and isinstance(config[field], dict):
            config[field] = normalize_locale_dict(config[field])
    return config


def load_categories(source, entries):
    """Load categories from category-list.json or auto-extract from entries."""
    cat_path = source / CATEGORY_LIST_FILE
    if cat_path.exists():
        with open(cat_path, "r", encoding="utf-8") as f:
            categories = json.load(f)
        for cat in categories:
            for field in ("name", "description"):
                if field in cat and isinstance(cat[field], dict):
                    cat[field] = normalize_locale_dict(cat[field])
        return categories

    seen = set()
    categories = []
    for entry in entries:
        cat = entry.get("category", "")
        if cat and cat not in seen:
            seen.add(cat)
            categories.append({"name": cat})
    return categories


def split_compose(compose_data):
    """Split parsed docker-compose.yml into clean compose + meta dict.

    Returns (compose_data, meta_dict, original_xcasaos).
    """
    xcasaos = compose_data.pop("x-casaos", {})

    if "port_map" in xcasaos and not isinstance(xcasaos["port_map"], str):
        xcasaos["port_map"] = str(xcasaos["port_map"])

    compose_xcasaos = {}
    meta = {}
    for key, value in xcasaos.items():
        if key in COMPOSE_KEEP_FIELDS:
            compose_xcasaos[key] = value
        else:
            meta[key] = value

    services = compose_data.get("services", {})
    if isinstance(services, dict):
        for svc_name, svc_def in services.items():
            if not isinstance(svc_def, dict):
                continue
            if "x-casaos" in svc_def:
                del svc_def["x-casaos"]
            labels = svc_def.get("labels", {})
            if isinstance(labels, dict) and "icon" in labels:
                del labels["icon"]
                if not labels:
                    del svc_def["labels"]

    compose_data["x-casaos"] = compose_xcasaos
    return compose_data, meta, xcasaos


# ---------------------------------------------------------------------------
# Per-app processing
# ---------------------------------------------------------------------------

def parse_app(app_dir):
    """Parse a single app directory and return raw data.

    Returns (app_id, compose_data, meta, original_xcasaos) or None if skipped.
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

    original_xcasaos = dict(compose_data.get("x-casaos", {}))
    app_id = resolve_app_id(compose_data, original_xcasaos, app_dir.name)

    compose_data, meta, _ = split_compose(compose_data)

    normalize_i18n_in_dict(compose_data.get("x-casaos", {}))
    normalize_i18n_in_dict(meta)
    normalize_i18n_in_dict(original_xcasaos)

    return app_id, compose_data, meta, original_xcasaos


def resolve_asset_filename(url_or_name, image_mapping, copied_images):
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


def write_locale_app(app_id, compose_data, meta, original_xcasaos,
                     locale, locale_output, assets_path,
                     icon_filename, copied_images, image_mapping, base_url):
    """Write single-language compose + meta for one app in one locale.

    Returns an index entry dict.
    """
    import copy
    compose_l = copy.deepcopy(compose_data)
    meta_l = copy.deepcopy(meta)

    # Resolve i18n fields in compose x-casaos
    xc = compose_l.get("x-casaos", {})
    if "title" in xc:
        xc["title"] = resolve_i18n(xc["title"], locale)
    xc["icon"] = url_join(base_url, f"{assets_path}/{icon_filename}")
    compose_l["x-casaos"] = xc

    # Resolve i18n fields in meta
    for field in I18N_FIELDS:
        if field in meta_l:
            meta_l[field] = resolve_i18n(meta_l[field], locale)
    for field in I18N_NESTED_FIELDS:
        if field in meta_l and isinstance(meta_l[field], dict):
            meta_l[field] = resolve_i18n_nested(meta_l[field], locale)

    # Remove icon from meta (stays in compose)
    meta_l.pop("icon", None)

    # Resolve image paths to assets/
    if "thumbnail" in meta_l:
        thumb_fname = resolve_asset_filename(meta_l["thumbnail"], image_mapping, copied_images)
        meta_l["thumbnail"] = f"{assets_path}/{thumb_fname}" if thumb_fname else ""
    if "screenshot_link" in meta_l:
        raw = meta_l["screenshot_link"]
        if raw and isinstance(raw, list):
            meta_l["screenshot_link"] = [
                f"{assets_path}/{resolve_asset_filename(u, image_mapping, copied_images)}"
                for u in raw
                if resolve_asset_filename(u, image_mapping, copied_images)
            ]
        else:
            meta_l["screenshot_link"] = []

    meta_l["base_url"] = normalize_base_url(base_url)

    # Write files
    app_output = locale_output / "apps" / app_id
    app_output.mkdir(parents=True, exist_ok=True)

    compose_content = yaml.dump(
        compose_l, default_flow_style=False, allow_unicode=True, sort_keys=False,
    )
    (app_output / "docker-compose.yml").write_text(compose_content, encoding="utf-8")

    meta_content = json.dumps(to_json_safe(meta_l), ensure_ascii=False, indent=2)
    (app_output / "meta.json").write_text(meta_content, encoding="utf-8")

    # Build index entry
    chash = content_hash(compose_content, meta_content)

    entry = {
        "id": app_id,
        "title": resolve_i18n(original_xcasaos.get("title", ""), locale),
        "tagline": resolve_i18n(original_xcasaos.get("tagline", ""), locale),
        "category": original_xcasaos.get("category", ""),
        "author": original_xcasaos.get("author", ""),
        "developer": original_xcasaos.get("developer", ""),
        "architectures": original_xcasaos.get("architectures", []),
        "icon": f"{assets_path}/{icon_filename}",
        "thumbnail": meta_l.get("thumbnail", ""),
        "compose_url": f"{locale}/apps/{app_id}/docker-compose.yml",
        "meta_url": f"{locale}/apps/{app_id}/meta.json",
        "content_hash": chash,
    }

    return entry


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    base_url = args.base_url

    print(f"Source: {source}")
    print(f"Output: {output}")
    print(f"Base URL: {base_url or '(relative)'}")
    print()

    # Clean output directory
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    apps_dir = source / "Apps"
    if not apps_dir.exists():
        print(f"Error: Apps directory not found at {apps_dir}", file=sys.stderr)
        sys.exit(1)

    # Load supported languages
    languages = load_supported_languages(source)
    print(f"Languages: {len(languages)} ({', '.join(languages)})")
    print()

    # Load store config
    store_config = load_store_config(source)
    if store_config:
        print(f"  STORE {store_config.get('store_id', '(unknown)')}")
    else:
        print(f"  WARN  {STORE_CONFIG_FILE} not found, skipping store.json")

    # ── Phase 1: Parse all apps and process assets ──
    print("\n── Processing apps ──")
    app_data_list = []  # list of (app_id, compose_data, meta, original_xcasaos, assets_info)
    skipped = []

    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue

        result = parse_app(app_dir)
        if result is None:
            skipped.append(app_dir.name)
            print(f"  SKIP {app_dir.name}")
            continue

        app_id, compose_data, meta, original_xcasaos = result

        # Process images into shared assets directory
        assets_app_dir = output / "assets" / "apps" / app_id
        copied_images, image_mapping, icon_filename = process_app_assets(app_dir, assets_app_dir)

        app_data_list.append((
            app_id, compose_data, meta, original_xcasaos,
            copied_images, image_mapping, icon_filename,
        ))
        print(f"  OK   {app_id}")

    # Sort by app_id for stable output
    app_data_list.sort(key=lambda x: x[0])

    # ── Phase 2: Generate per-language output ──
    print(f"\n── Generating {len(languages)} language outputs ──")

    for locale in languages:
        locale_output = output / locale
        locale_output.mkdir(parents=True, exist_ok=True)

        # Write store.json for this locale
        if store_config:
            store_l = {
                "version": store_config.get("version", 2),
                "store_id": store_config.get("store_id", ""),
                "name": resolve_i18n(store_config.get("name", ""), locale),
                "description": resolve_i18n(store_config.get("description", ""), locale),
                "maintainer": store_config.get("maintainer", ""),
                "url": store_config.get("url", ""),
            }
            (locale_output / "store.json").write_text(
                json.dumps(store_l, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        # Write per-app files and collect index entries
        entries = []
        for (app_id, compose_data, meta, original_xcasaos,
             copied_images, image_mapping, icon_filename) in app_data_list:

            assets_path = f"assets/apps/{app_id}"
            entry = write_locale_app(
                app_id, compose_data, meta, original_xcasaos,
                locale, locale_output, assets_path,
                icon_filename, copied_images, image_mapping, base_url,
            )
            entries.append(entry)

        # Write index.json for this locale
        index = {
            "version": 2,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "app_count": len(entries),
            "base_url": normalize_base_url(base_url),
            "apps": entries,
        }
        index_path = locale_output / "index.json"
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(f"  {locale}: {len(entries)} apps, index {index_path.stat().st_size / 1024:.1f} KB")

    # ── Summary ──
    print(f"\n{'='*50}")
    print(f"Done! {len(app_data_list)} apps × {len(languages)} languages")
    print(f"Output: {output}/")
    print(f"  assets/     (shared images)")
    for locale in languages:
        lp = output / locale / "index.json"
        size = f"{lp.stat().st_size / 1024:.1f} KB" if lp.exists() else "?"
        print(f"  {locale}/    (index: {size})")
    print(f"  categories  (removed from output)")
    if skipped:
        print(f"  Skipped: {', '.join(skipped)}")


if __name__ == "__main__":
    main()

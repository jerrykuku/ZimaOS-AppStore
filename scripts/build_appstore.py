#!/usr/bin/env python3
"""
Build script for ZimaOS AppStore online metadata.

Generates a flat output layout:

  dist/
    index.json
    index.{locale}.json            # only when locale is explicitly defined in app i18n
    store.json
    store.{locale}.json            # only when locale is explicitly defined in store i18n
    apps/{app_id}/
      docker-compose.yml
      meta.json
      meta.{locale}.json           # only when locale is explicitly defined in app i18n
      assets/
        icon.svg
        thumbnail.webp
        screenshot-1.webp
"""

import argparse
import copy
import hashlib
import json
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

# Supported languages config filename
SUPPORTED_LANGUAGES_FILE = "supported-languages.json"

# Default / fallback locale
DEFAULT_LOCALE = "en_US"

# Fields in x-casaos that contain i18n locale dicts
I18N_FIELDS = {"title", "tagline", "description", "releaseNotes"}
# Fields that contain nested i18n dicts (e.g. tips.before_install)
I18N_NESTED_FIELDS = {"tips"}

# Index-level i18n fields
INDEX_I18N_FIELDS = {"title", "tagline"}


# ---------------------------------------------------------------------------
# Arguments / utility helpers
# ---------------------------------------------------------------------------

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


def content_hash(*parts):
    """Compute a short SHA-256 hash over multiple content strings/bytes."""
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, str):
            p = p.encode("utf-8")
        h.update(p)
    return h.hexdigest()[:8]


def hash_directory_files(root_dir):
    """Compute a stable short hash from all files under a directory."""
    h = hashlib.sha256()
    files = sorted(
        p for p in root_dir.rglob("*")
        if p.is_file()
    )
    for file_path in files:
        rel = file_path.relative_to(root_dir).as_posix().encode("utf-8")
        h.update(rel)
        h.update(b"\0")
        h.update(file_path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:8]


def normalize_base_url(base):
    """Normalize base URL without trailing '/'."""
    if not base:
        return ""
    return base.rstrip("/")


def url_join(base, path):
    """Join base URL and path where path should start with '/'."""
    path = path if str(path).startswith("/") else f"/{path}"
    if not base:
        return path
    return f"{base.rstrip('/')}{path}"


def normalize_locale_key(key):
    """Normalize locale key to ll_CC format (e.g. en_us -> en_US)."""
    parts = key.split("_", 1)
    if len(parts) == 2:
        return f"{parts[0].lower()}_{parts[1].upper()}"
    return key


def normalize_locale_dict(d):
    """Normalize locale keys in i18n dicts."""
    if not isinstance(d, dict):
        return d
    return {normalize_locale_key(k): v for k, v in d.items()}


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
    """Resolve an i18n dict to plain text with fallback chain."""
    if not isinstance(value, dict):
        return value if value is not None else ""
    if locale in value:
        return value[locale]
    if DEFAULT_LOCALE in value:
        return value[DEFAULT_LOCALE]
    return next(iter(value.values()), "")


def resolve_i18n_strict(value, locale):
    """Resolve i18n without fallback; return empty string when locale missing."""
    if not isinstance(value, dict):
        return value if value is not None else ""
    return value.get(locale, "")


def resolve_i18n_nested(value, locale, strict=False):
    """Resolve a nested i18n structure (like tips) for a given locale."""
    if not isinstance(value, dict):
        return value
    resolver = resolve_i18n_strict if strict else resolve_i18n
    result = {}
    for key, sub_val in value.items():
        result[key] = resolver(sub_val, locale)
    return result


def collect_locales_from_i18n(data, fields=None, nested_fields=None):
    """Collect explicitly defined locales from i18n dict fields."""
    if not isinstance(data, dict):
        return set()

    fields = fields or I18N_FIELDS
    nested_fields = nested_fields or I18N_NESTED_FIELDS
    locales = set()

    for field in fields:
        value = data.get(field)
        if isinstance(value, dict):
            locales.update(value.keys())

    for field in nested_fields:
        value = data.get(field)
        if not isinstance(value, dict):
            continue
        for sub_val in value.values():
            if isinstance(sub_val, dict):
                locales.update(sub_val.keys())

    return locales


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
        print(
            f"  WARN  {SUPPORTED_LANGUAGES_FILE} not found, using {DEFAULT_LOCALE} only",
            file=sys.stderr,
        )
        return [DEFAULT_LOCALE]
    with open(lang_path, "r", encoding="utf-8") as f:
        languages = json.load(f)
    if DEFAULT_LOCALE not in languages:
        languages.insert(0, DEFAULT_LOCALE)
    return [normalize_locale_key(l) for l in languages]


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------

def optimize_and_convert_image(src_path, dst_path, max_width=MAX_IMAGE_WIDTH, quality=WEBP_QUALITY):
    """Optimize and convert image to WebP format. Returns output filename."""
    if not PILLOW_AVAILABLE:
        shutil.copy2(src_path, dst_path)
        return dst_path.name

    src_ext = src_path.suffix.lower()

    if src_ext == ".svg":
        shutil.copy2(src_path, dst_path)
        return dst_path.name

    if src_ext == ".webp":
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
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

            webp_path = dst_path.with_suffix(".webp")
            img.save(webp_path, "WEBP", quality=quality, method=6)
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


def process_app_assets(app_dir, assets_output):
    """Process images for a single app into apps/{app_id}/assets.

    Returns (copied_images, image_mapping, icon_filename).
    """
    assets_output.mkdir(parents=True, exist_ok=True)

    copied_images = []
    image_mapping = {}
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
            shutil.copy2(img_file, dst_path)
            copied_images.append(img_file.name)
            image_mapping[img_file.name] = img_file.name
        else:
            output_name = optimize_and_convert_image(img_file, dst_path)
            copied_images.append(output_name)
            image_mapping[img_file.name] = output_name

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


def split_compose(compose_data):
    """Split parsed docker-compose.yml into clean compose + meta dict."""
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
        for svc_def in services.values():
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
    return compose_data, meta


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

    compose_data, meta = split_compose(compose_data)

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


def build_meta_payload(meta, locale, assets_path, copied_images, image_mapping, base_url, strict=False):
    """Build locale-resolved meta payload."""
    meta_l = copy.deepcopy(meta)

    resolver = resolve_i18n_strict if strict else resolve_i18n
    for field in I18N_FIELDS:
        if field in meta_l:
            meta_l[field] = resolver(meta_l[field], locale)
    for field in I18N_NESTED_FIELDS:
        if field in meta_l and isinstance(meta_l[field], dict):
            meta_l[field] = resolve_i18n_nested(meta_l[field], locale, strict=strict)

    meta_l.pop("icon", None)

    if "thumbnail" in meta_l:
        thumb_fname = resolve_asset_filename(meta_l["thumbnail"], image_mapping, copied_images)
        meta_l["thumbnail"] = f"{assets_path}/{thumb_fname}" if thumb_fname else ""
    if "screenshot_link" in meta_l:
        raw = meta_l["screenshot_link"]
        if raw and isinstance(raw, list):
            meta_l["screenshot_link"] = [
                f"{assets_path}/{resolved}"
                for u in raw
                for resolved in [resolve_asset_filename(u, image_mapping, copied_images)]
                if resolved
            ]
        else:
            meta_l["screenshot_link"] = []

    meta_l["base_url"] = normalize_base_url(base_url)
    return meta_l


def build_meta_i18n_overlay(app_id, meta, locale):
    """Build locale overlay meta file with id + i18n-only fields."""
    out = {"id": app_id}
    for field in I18N_FIELDS:
        value = meta.get(field)
        if isinstance(value, dict) and locale in value:
            out[field] = value[locale]
    for field in I18N_NESTED_FIELDS:
        value = meta.get(field)
        if not isinstance(value, dict):
            continue
        nested = {}
        for sub_key, sub_val in value.items():
            if isinstance(sub_val, dict) and locale in sub_val:
                nested[sub_key] = sub_val[locale]
        if nested:
            out[field] = nested
    return out


def build_index_entry(app_id, original_xcasaos, locale, assets_path, icon_filename,
                      thumbnail, compose_url, meta_url, content_hash_value, strict=False):
    """Build one index entry for a locale."""
    resolver = resolve_i18n_strict if strict else resolve_i18n
    return {
        "id": app_id,
        "title": resolver(original_xcasaos.get("title", ""), locale),
        "tagline": resolver(original_xcasaos.get("tagline", ""), locale),
        "category": original_xcasaos.get("category", ""),
        "version": original_xcasaos.get("version") or "",
        "author": original_xcasaos.get("author", ""),
        "developer": original_xcasaos.get("developer", ""),
        "architectures": original_xcasaos.get("architectures", []),
        "icon": f"{assets_path}/{icon_filename}",
        "thumbnail": thumbnail,
        "compose_url": compose_url,
        "meta_url": meta_url,
        "content_hash": content_hash_value,
    }


def build_index_i18n_overlay_entry(app_id, original_xcasaos, locale):
    """Build locale overlay index entry with id + i18n-only fields."""
    out = {"id": app_id}
    for field in INDEX_I18N_FIELDS:
        value = original_xcasaos.get(field)
        if isinstance(value, dict) and locale in value:
            out[field] = value[locale]
    return out


def build_store_i18n_overlay(store_config, locale):
    """Build locale overlay store file with store_id + i18n-only fields."""
    out = {"store_id": store_config.get("store_id", "")}
    for field in ("name", "description"):
        value = store_config.get(field)
        if isinstance(value, dict) and locale in value:
            out[field] = value[locale]
    return out


def write_json(path, data):
    path.write_text(json.dumps(to_json_safe(data), ensure_ascii=False, indent=2), encoding="utf-8")


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

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    apps_dir = source / "Apps"
    if not apps_dir.exists():
        print(f"Error: Apps directory not found at {apps_dir}", file=sys.stderr)
        sys.exit(1)

    languages = load_supported_languages(source)
    supported_locales = set(languages)
    print(f"Languages (candidate): {len(languages)} ({', '.join(languages)})")
    print()

    store_config = load_store_config(source)
    if store_config:
        print(f"  STORE {store_config.get('store_id', '(unknown)')}")
    else:
        print(f"  WARN  {STORE_CONFIG_FILE} not found, skipping store.json")

    print("\n── Processing apps ──")
    app_records = []
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

        app_output = output / "apps" / app_id
        assets_output = app_output / "assets"
        copied_images, image_mapping, icon_filename = process_app_assets(app_dir, assets_output)

        assets_path = f"/apps/{app_id}/assets"

        compose_l = copy.deepcopy(compose_data)
        compose_xc = compose_l.get("x-casaos", {})
        if "title" in compose_xc:
            compose_xc["title"] = resolve_i18n(compose_xc["title"], DEFAULT_LOCALE)
        compose_xc["icon"] = url_join(base_url, f"{assets_path}/{icon_filename}")
        compose_l["x-casaos"] = compose_xc

        app_output.mkdir(parents=True, exist_ok=True)
        compose_content = yaml.dump(
            compose_l,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        compose_path = app_output / "docker-compose.yml"
        compose_path.write_text(compose_content, encoding="utf-8")

        meta_default = build_meta_payload(
            meta,
            DEFAULT_LOCALE,
            assets_path,
            copied_images,
            image_mapping,
            base_url,
            strict=False,
        )
        meta_default_content = json.dumps(to_json_safe(meta_default), ensure_ascii=False, indent=2)
        (app_output / "meta.json").write_text(meta_default_content, encoding="utf-8")

        meta_locales = collect_locales_from_i18n(meta)
        meta_locales = {
            loc for loc in meta_locales
            if loc in supported_locales and loc != DEFAULT_LOCALE
        }
        for locale in sorted(meta_locales):
            meta_locale = build_meta_i18n_overlay(app_id, meta, locale)
            write_json(app_output / f"meta.{locale}.json", meta_locale)

        chash = hash_directory_files(app_output)

        index_locales = collect_locales_from_i18n(
            original_xcasaos,
            fields=INDEX_I18N_FIELDS,
            nested_fields=set(),
        )
        index_locales = {
            loc for loc in index_locales
            if loc in supported_locales and loc != DEFAULT_LOCALE
        }

        app_records.append({
            "app_id": app_id,
            "original_xcasaos": original_xcasaos,
            "assets_path": assets_path,
            "icon_filename": icon_filename,
            "thumbnail": meta_default.get("thumbnail", ""),
            "content_hash": chash,
            "index_locales": index_locales,
        })
        print(f"  OK   {app_id}")

    app_records.sort(key=lambda x: x["app_id"])

    print("\n── Generating store/index files ──")

    if store_config:
        store_default = {
            "version": store_config.get("version", 2),
            "store_id": store_config.get("store_id", ""),
            "name": resolve_i18n(store_config.get("name", ""), DEFAULT_LOCALE),
            "description": resolve_i18n(store_config.get("description", ""), DEFAULT_LOCALE),
            "maintainer": store_config.get("maintainer", ""),
            "url": store_config.get("url", ""),
        }
        write_json(output / "store.json", store_default)

        store_locales = set()
        for field in ("name", "description"):
            value = store_config.get(field)
            if isinstance(value, dict):
                store_locales.update(value.keys())
        store_locales = {
            loc for loc in store_locales
            if loc in supported_locales and loc != DEFAULT_LOCALE
        }

        for locale in sorted(store_locales):
            store_locale = build_store_i18n_overlay(store_config, locale)
            write_json(output / f"store.{locale}.json", store_locale)
            print(f"  store.{locale}.json")

    default_entries = []
    for record in app_records:
        app_id = record["app_id"]
        default_entries.append(
            build_index_entry(
                app_id=app_id,
                original_xcasaos=record["original_xcasaos"],
                locale=DEFAULT_LOCALE,
                assets_path=record["assets_path"],
                icon_filename=record["icon_filename"],
                thumbnail=record["thumbnail"],
                compose_url=f"/apps/{app_id}/docker-compose.yml",
                meta_url=f"/apps/{app_id}/meta.json",
                content_hash_value=record["content_hash"],
                strict=False,
            )
        )

    index_default = {
        "version": 2,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "app_count": len(default_entries),
        "base_url": normalize_base_url(base_url),
        "apps": default_entries,
    }
    write_json(output / "index.json", index_default)

    candidate_index_locales = set()
    for record in app_records:
        candidate_index_locales.update(record["index_locales"])

    for locale in sorted(candidate_index_locales):
        locale_entries = []
        for record in app_records:
            if locale not in record["index_locales"]:
                continue
            app_id = record["app_id"]
            entry = build_index_i18n_overlay_entry(
                app_id=app_id,
                original_xcasaos=record["original_xcasaos"],
                locale=locale,
            )
            # Keep sparse locale files: id + explicitly translated i18n fields only.
            if len(entry) > 1:
                locale_entries.append(entry)

        if not locale_entries:
            continue

        index_locale = {"apps": locale_entries}
        write_json(output / f"index.{locale}.json", index_locale)
        print(f"  index.{locale}.json ({len(locale_entries)} apps)")

    print(f"\n{'=' * 50}")
    print(f"Done! {len(app_records)} apps")
    print(f"Output: {output}/")
    print("  index.json")
    print("  index.{locale}.json (only when locale is explicitly defined)")
    print("  store.json / store.{locale}.json")
    print("  apps/{app_id}/docker-compose.yml")
    print("  apps/{app_id}/meta.json / meta.{locale}.json")
    print("  apps/{app_id}/assets/*")
    if skipped:
        print(f"  Skipped: {', '.join(skipped)}")


if __name__ == "__main__":
    main()

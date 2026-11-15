import json
import os
import re
import tempfile
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTLINE_COLOR = "#101416"


@dataclass
class Crosshair:
    shape: str = "Cross"
    color: str = "#E8FF45"
    outline_color: str = DEFAULT_OUTLINE_COLOR
    glow_enabled: bool = False
    glow_color: str = "#00E5FF"
    glow_size: int = 8
    glow_strength: int = 65
    size: int = 24
    vertical_size: int = 24
    gap: int = 6
    thickness: int = 3
    outline: int = 1
    opacity: int = 100
    center_dot: bool = True
    dot_size: int = 3
    offset_x: int = 0
    offset_y: int = 0
    image_path: str = ""
    image_scale: int = 100
    remove_background: bool = False
    bg_tolerance: int = 30


# size / vertical_size are arm lengths NOT counting the gap (see crosshair_render.py).
PRESETS = {
    "CLASSIC": Crosshair(size=18, vertical_size=18),
    "PRECISION": Crosshair(color="#F5F7F2", size=11, vertical_size=11, gap=7, thickness=2),
    "COMPACT": Crosshair(shape="T", color="#65E6D2", size=13, vertical_size=13, gap=4, thickness=2),
    "DOT": Crosshair(shape="Dot", color="#FF6F59", size=8, vertical_size=8, gap=0, thickness=2, center_dot=False),
    "MINIMAL": Crosshair(color="#F5F7F2", size=9, vertical_size=9, gap=5, thickness=1, outline=0, center_dot=False),
    "SMALL": Crosshair(color="#7DFF8A", size=12, vertical_size=12, gap=4, thickness=2, outline=0, center_dot=False),
    "WIDE": Crosshair(color="#E8FF45", size=26, vertical_size=18, gap=8, thickness=3, center_dot=False),
    "HIGH VISIBILITY": Crosshair(color="#FF5A36", size=24, vertical_size=24, gap=4, thickness=5, outline=2),
    "TAPPING": Crosshair(color="#69E1FF", size=12, vertical_size=12, gap=6, thickness=2),
    "SPRAY CONTROL": Crosshair(shape="T", color="#E8FF45", size=22, vertical_size=19, gap=3, thickness=3, center_dot=False),
    "SNIPER FRIENDLY": Crosshair(shape="Dot", color="#FFFFFF", size=4, vertical_size=4, gap=0, thickness=1, center_dot=False),
    "LOW DISTRACTION": Crosshair(color="#F5F7F2", size=11, vertical_size=11, gap=6, thickness=1, outline=0, opacity=70, center_dot=False),
    "NEON RING": Crosshair(shape="Circle", color="#69E1FF", size=26, vertical_size=26, gap=0, thickness=2, outline=1, center_dot=False),
    "PRO GREEN": Crosshair(color="#39FF14", size=15, vertical_size=15, gap=5, thickness=2, outline=1, center_dot=True, dot_size=2),
    "BIG DOT": Crosshair(shape="Dot", color="#39FF14", size=12, vertical_size=12, gap=0, thickness=2, outline=1, center_dot=False),
    "SHOTGUN RING": Crosshair(shape="Circle", color="#FF5A36", size=44, vertical_size=44, gap=0, thickness=2, outline=1, center_dot=False),
    "NEON EDGE": Crosshair(color="#E8FF45", size=19, vertical_size=19, gap=5, thickness=3, outline=2, outline_color="#FF00E6"),
    "NEON CYAN": Crosshair(color="#8CFFFF", outline_color="#123443", glow_enabled=True,
                           glow_color="#00E5FF", size=18, vertical_size=18, gap=5, thickness=3, outline=2),
    "NEON PINK": Crosshair(color="#FF75D8", outline_color="#40142F", glow_enabled=True,
                           glow_color="#FF2D95", size=18, vertical_size=18, gap=5, thickness=3, outline=2),
    "NEON LIME": Crosshair(color="#C8FF00", outline_color="#263414", glow_enabled=True,
                           glow_color="#80FF00", size=18, vertical_size=18, gap=5, thickness=3, outline=2),
    "FROST BITE": Crosshair(color="#FFFFFF", size=16, vertical_size=16, gap=5, thickness=2, outline=2, outline_color="#2E7BFF", center_dot=False),
}


SHAPES = {"Cross", "Dot", "T", "Circle", "Image"}
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
SETTINGS_FIELDS = set(asdict(Crosshair()))
COLOR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}\Z")


def validate_settings(values: dict[str, Any] | Crosshair) -> Crosshair:
    source = asdict(values) if isinstance(values, Crosshair) else values
    if not isinstance(source, dict):
        raise ValueError("Crosshair settings must be an object.")
    defaults = asdict(Crosshair())
    defaults.update({key: value for key, value in source.items() if key in SETTINGS_FIELDS})
    if defaults["shape"] not in SHAPES:
        raise ValueError("Shape must be Cross, Dot, T, Circle, or Image.")
    if not isinstance(defaults["color"], str) or not COLOR_PATTERN.fullmatch(defaults["color"]):
        raise ValueError("Color must be a six-digit HEX value such as #E8FF45.")
    if not isinstance(defaults["outline_color"], str) or not COLOR_PATTERN.fullmatch(defaults["outline_color"]):
        raise ValueError("Outline color must be a six-digit HEX value such as #101416.")
    if not isinstance(defaults["glow_color"], str) or not COLOR_PATTERN.fullmatch(defaults["glow_color"]):
        raise ValueError("Glow color must be a six-digit HEX value such as #00E5FF.")
    if not isinstance(defaults["center_dot"], bool):
        raise ValueError("Center dot must be true or false.")
    if not isinstance(defaults["glow_enabled"], bool):
        raise ValueError("Glow enabled must be true or false.")
    bounds = {
        "size": (1, 80),
        "vertical_size": (1, 80),
        "gap": (0, 40),
        "thickness": (1, 12),
        "outline": (0, 6),
        "opacity": (0, 100),
        "dot_size": (1, 20),
        "offset_x": (-200, 200),
        "offset_y": (-200, 200),
        "image_scale": (10, 400),
        "bg_tolerance": (0, 100),
        "glow_size": (1, 16),
        "glow_strength": (0, 100),
    }
    for key, (minimum, maximum) in bounds.items():
        value = defaults[key]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{key.replace('_', ' ').title()} must be an integer from {minimum} to {maximum}.")
    if not isinstance(defaults["image_path"], str):
        raise ValueError("Image path must be text.")
    if not isinstance(defaults["remove_background"], bool):
        raise ValueError("Remove background must be true or false.")
    if defaults["shape"] == "Image" and not defaults["image_path"]:
        raise ValueError("A custom image crosshair needs an image file.")
    if defaults["shape"] == "Image":
        path = Path(defaults["image_path"])
        if not path.is_file():
            raise ValueError("The selected image file could not be found.")
        if path.suffix.casefold() not in IMAGE_EXTENSIONS:
            raise ValueError("Choose a PNG, JPG, BMP, GIF or WebP image.")
    return Crosshair(**defaults)


class ProfileStore:
    FORMAT_VERSION = 1
    MAX_ARCHIVE_PROFILES = 500
    MAX_PROFILE_BYTES = 1_000_000

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _read(self) -> list[dict[str, Any]]:
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read the profile library: {error}") from error
        if not isinstance(content, dict) or content.get("format_version") != self.FORMAT_VERSION:
            raise ValueError("The profile library has an unsupported format.")
        records = content.get("profiles")
        if not isinstance(records, list):
            raise ValueError("The profile library is missing its profiles list.")
        for record in records:
            self._validate_record(record)
        return records

    @staticmethod
    def _validate_record(record: Any) -> None:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ValueError("A profile record is invalid.")
        if not isinstance(record.get("name"), str) or not record["name"].strip():
            raise ValueError("A profile name is missing.")
        if not isinstance(record.get("description", ""), str):
            raise ValueError("A profile description is invalid.")
        if not isinstance(record.get("tags", []), list) or not all(isinstance(tag, str) for tag in record.get("tags", [])):
            raise ValueError("Profile tags must be a list of text values.")
        if not isinstance(record.get("favorite", False), bool):
            raise ValueError("Profile favorite flag must be true or false.")
        validate_settings(record.get("settings"))

    def _write(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp") as temporary:
                temporary_path = temporary.name
                json.dump({"format_version": self.FORMAT_VERSION, "profiles": records}, temporary, indent=2)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        except OSError as error:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
            raise ValueError(f"Could not save the profile library: {error}") from error

    @staticmethod
    def _clean_metadata(name: str, description: str, tags: list[str] | tuple[str, ...]) -> tuple[str, str, list[str]]:
        clean_name = name.strip()
        clean_description = description.strip()
        clean_tags = list(dict.fromkeys(tag.strip()[:32] for tag in tags if tag.strip()))[:20]
        if not clean_name or len(clean_name) > 80:
            raise ValueError("Profile names must contain 1 to 80 characters.")
        if len(clean_description) > 500:
            raise ValueError("Descriptions must be 500 characters or fewer.")
        return clean_name, clean_description, clean_tags

    def save(
        self,
        name: str,
        settings: dict[str, Any] | Crosshair,
        description: str = "",
        tags: list[str] | tuple[str, ...] = (),
        profile_id: str | None = None,
        favorite: bool = False,
    ) -> dict[str, Any]:
        clean_name, clean_description, clean_tags = self._clean_metadata(name, description, tags)
        clean_settings = asdict(validate_settings(settings))
        records = self._read()
        existing = next((item for item in records if item["id"] == profile_id), None) if profile_id else None
        if profile_id and existing is None:
            raise ValueError("The selected profile no longer exists.")
        if any(item["id"] != profile_id and item["name"].casefold() == clean_name.casefold() for item in records):
            raise ValueError(f'A profile named "{clean_name}" already exists.')
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if existing:
            existing.update(name=clean_name, description=clean_description, tags=clean_tags, settings=clean_settings, modified_utc=now)
            existing["favorite"] = bool(favorite if favorite is not None else existing.get("favorite", False))
            record = existing
        else:
            record = {
                "id": uuid.uuid4().hex,
                "name": clean_name,
                "description": clean_description,
                "tags": clean_tags,
                "favorite": bool(favorite),
                "settings": clean_settings,
                "created_utc": now,
                "modified_utc": now,
            }
            records.append(record)
        self._write(records)
        return dict(record)

    def list_profiles(self, query: str = "", sort: str = "modified") -> list[dict[str, Any]]:
        records = self._read()
        needle = query.strip().casefold()
        if needle:
            records = [record for record in records if needle in " ".join([record["name"], record.get("description", ""), *record.get("tags", [])]).casefold()]
        if sort == "name":
            records.sort(key=lambda item: item["name"].casefold())
        elif sort == "favorites":
            records.sort(key=lambda item: (not item.get("favorite", False), -self._timestamp(item)))
        else:
            records.sort(key=self._timestamp, reverse=True)
        return records

    @staticmethod
    def _timestamp(record: dict[str, Any]) -> float:
        try:
            return datetime.fromisoformat(record.get("modified_utc", "")).timestamp()
        except (ValueError, TypeError, OSError):
            return 0.0

    def get(self, profile_id: str) -> dict[str, Any]:
        record = next((item for item in self._read() if item["id"] == profile_id), None)
        if record is None:
            raise ValueError("The selected profile no longer exists.")
        return dict(record)

    def delete(self, profile_id: str) -> None:
        records = self._read()
        remaining = [record for record in records if record["id"] != profile_id]
        if len(remaining) == len(records):
            raise ValueError("The selected profile no longer exists.")
        self._write(remaining)

    def set_favorite(self, profile_id: str, favorite: bool) -> dict[str, Any]:
        record = self.get(profile_id)
        return self.save(record["name"], record["settings"], record.get("description", ""), record.get("tags", []), profile_id, favorite)

    def duplicate(self, profile_id: str, name: str | None = None) -> dict[str, Any]:
        source = self.get(profile_id)
        return self.save(name or f'{source["name"]} Copy', source["settings"], source.get("description", ""), source.get("tags", []))

    def export_profile(self, profile_id: str, destination: Path | str) -> None:
        record = self.get(profile_id)
        Path(destination).write_text(json.dumps({"format": "sightline-profile", **record}, indent=2), encoding="utf-8")

    def import_profile(self, source: Path | str) -> dict[str, Any]:
        path = Path(source)
        try:
            raw = path.read_bytes()
            if len(raw) > self.MAX_PROFILE_BYTES:
                raise ValueError("Profile file is too large.")
            content = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not import this profile: {error}") from error
        if not isinstance(content, dict):
            raise ValueError("Profile JSON must contain an object.")
        raw_settings = content.get("settings", content)
        if not isinstance(raw_settings, dict) or not raw_settings.keys() & SETTINGS_FIELDS:
            raise ValueError("No supported crosshair settings were found.")
        settings = validate_settings(raw_settings)
        name = str(content.get("name") or path.stem)
        description = str(content.get("description", ""))
        tags = content.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError("Profile tags must be a list of text values.")
        name = self._unique_name(name)
        return self.save(name, settings, description, tags, favorite=bool(content.get("favorite", False)))

    def export_archive(self, destination: Path | str) -> None:
        records = self._read()
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for record in records:
                payload = json.dumps({"format": "sightline-profile", **record}, indent=2)
                archive.writestr(f'{record["id"]}.json', payload)

    def import_archive(self, source: Path | str) -> list[dict[str, Any]]:
        try:
            with zipfile.ZipFile(source, "r") as archive:
                files = [item for item in archive.infolist() if not item.is_dir() and item.filename.casefold().endswith(".json")]
                if len(files) > self.MAX_ARCHIVE_PROFILES:
                    raise ValueError("The archive contains too many profile files.")
                parsed: list[tuple[str, str, list[str], Crosshair, bool]] = []
                for item in files:
                    if item.file_size > self.MAX_PROFILE_BYTES:
                        raise ValueError(f"Profile file {item.filename} is too large.")
                    data = json.loads(archive.read(item).decode("utf-8"))
                    if not isinstance(data, dict):
                        raise ValueError(f"Profile file {item.filename} is invalid.")
                    raw_settings = data.get("settings", data)
                    if not isinstance(raw_settings, dict) or not raw_settings.keys() & SETTINGS_FIELDS:
                        raise ValueError(f"No crosshair settings were found in {item.filename}.")
                    settings = validate_settings(raw_settings)
                    name = self._unique_name(str(data.get("name") or Path(item.filename).stem))
                    tags = data.get("tags", [])
                    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                        raise ValueError(f"Profile tags in {item.filename} are invalid.")
                    description = data.get("description", "")
                    favorite = data.get("favorite", False)
                    if not isinstance(description, str) or not isinstance(favorite, bool):
                        raise ValueError(f"Profile metadata in {item.filename} is invalid.")
                    parsed.append((name, description, tags, settings, favorite))
                imported: list[dict[str, Any]] = []
                records = self._read()
                names = {record["name"].casefold() for record in records}
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                for name, description, tags, settings, favorite in parsed:
                    candidate = name.strip() or "Imported Profile"
                    base = candidate
                    suffix = 2
                    while candidate.casefold() in names:
                        candidate = f"{base} ({suffix})"
                        suffix += 1
                    clean_name, clean_description, clean_tags = self._clean_metadata(candidate, description, tags)
                    record = {
                        "id": uuid.uuid4().hex,
                        "name": clean_name,
                        "description": clean_description,
                        "tags": clean_tags,
                        "favorite": favorite,
                        "settings": asdict(settings),
                        "created_utc": now,
                        "modified_utc": now,
                    }
                    names.add(clean_name.casefold())
                    records.append(record)
                    imported.append(dict(record))
                if imported:
                    self._write(records)
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not import this profile archive: {error}") from error
        return imported

    def _unique_name(self, name: str) -> str:
        existing = {item["name"].casefold() for item in self._read()}
        candidate = name.strip() or "Imported Profile"
        if candidate.casefold() not in existing:
            return candidate
        number = 2
        while f"{candidate} ({number})".casefold() in existing:
            number += 1
        return f"{candidate} ({number})"


@dataclass
class CS2Import:
    settings: Crosshair
    detected: list[str]
    warnings: list[str]


CS2_COMMAND = re.compile(r"\b(cl_crosshair[a-z0-9_]+)\s*(?:=|\s)\s*(?:\"([^\"]*)\"|'([^']*)'|([^;\s]+))", re.IGNORECASE)
CS2_SUPPORTED = {
    "cl_crosshairstyle", "cl_crosshairsize", "cl_crosshairgap", "cl_crosshairthickness",
    "cl_crosshair_drawoutline", "cl_crosshair_outlinethickness", "cl_crosshairdot", "cl_crosshair_t",
    "cl_crosshairalpha", "cl_crosshaircolor", "cl_crosshaircolor_r", "cl_crosshaircolor_g", "cl_crosshaircolor_b",
}
CS2_COLORS = {"0": "#FF0000", "1": "#00FF00", "2": "#FFFF00", "3": "#0000FF", "4": "#00FFFF"}


def parse_cs2_commands(text: str) -> CS2Import:
    cleaned = re.sub(r"(?m)//.*$", "", text)
    values: dict[str, str] = {}
    warnings: list[str] = []
    for match in CS2_COMMAND.finditer(cleaned):
        key = match.group(1).lower()
        value = next((part for part in match.groups()[1:] if part is not None), "").strip()
        if key not in CS2_SUPPORTED:
            warnings.append(f"Unsupported command ignored: {key}")
        else:
            values[key] = value
    if not values:
        raise ValueError("No supported CS2 crosshair commands were found.")

    settings = Crosshair()
    detected: list[str] = []

    def number(key: str, default: int, minimum: int, maximum: int) -> int:
        if key not in values:
            return default
        try:
            parsed = int(round(float(values[key])))
        except ValueError:
            warnings.append(f"Invalid number for {key}: {values[key]}")
            return default
        bounded = max(minimum, min(maximum, parsed))
        if bounded != parsed:
            warnings.append(f"{key} was clamped to the supported Sightline range.")
        detected.append(key)
        return bounded

    style = values.get("cl_crosshairstyle")
    if style is not None:
        detected.append("cl_crosshairstyle")
        if style in {"0", "1", "2", "3", "4", "5"}:
            if style in {"0", "1", "2", "3"}:
                warnings.append("Animated or legacy CS2 styles are approximated as a static Sightline crosshair.")
            elif style == "5":
                warnings.append("CS2 follow-recoil behavior cannot be represented by a static Sightline crosshair.")
        else:
            warnings.append(f"CS2 style {style} is unsupported and was approximated as a static crosshair.")

    settings.size = number("cl_crosshairsize", settings.size, 1, 80)
    settings.vertical_size = settings.size
    settings.gap = number("cl_crosshairgap", settings.gap, 0, 40)
    settings.thickness = number("cl_crosshairthickness", settings.thickness, 1, 12)
    settings.outline = number("cl_crosshair_outlinethickness", settings.outline, 0, 6)
    settings.opacity = round(number("cl_crosshairalpha", 255, 0, 255) * 100 / 255)
    if "cl_crosshairalpha" not in values:
        settings.opacity = Crosshair().opacity
    else:
        detected.append("cl_crosshairalpha")

    if "cl_crosshair_drawoutline" in values:
        settings.outline = settings.outline if values["cl_crosshair_drawoutline"] not in {"0", "false"} else 0
        detected.append("cl_crosshair_drawoutline")
    if "cl_crosshairdot" in values:
        settings.center_dot = values["cl_crosshairdot"] not in {"0", "false"}
        detected.append("cl_crosshairdot")
    if "cl_crosshair_t" in values and values["cl_crosshair_t"] not in {"0", "false"}:
        settings.shape = "T"
        detected.append("cl_crosshair_t")

    rgb_keys = ("cl_crosshaircolor_r", "cl_crosshaircolor_g", "cl_crosshaircolor_b")
    if all(key in values for key in rgb_keys):
        rgb = [number(key, 255, 0, 255) for key in rgb_keys]
        settings.color = "#" + "".join(f"{channel:02X}" for channel in rgb)
    elif "cl_crosshaircolor" in values:
        color_code = values["cl_crosshaircolor"]
        if color_code in CS2_COLORS:
            settings.color = CS2_COLORS[color_code]
            detected.append("cl_crosshaircolor")
        elif color_code == "5":
            warnings.append("Custom CS2 color selected without complete RGB values; Sightline kept its default color.")
        else:
            warnings.append(f"Unknown CS2 color code {color_code}; Sightline kept its default color.")

    missing = [key for key in ("cl_crosshairstyle", "cl_crosshairsize", "cl_crosshairgap", "cl_crosshairthickness") if key not in values]
    if missing:
        warnings.append("Missing settings use Sightline defaults: " + ", ".join(missing))
    warnings.append("CS2 uses game-specific rendering units; imported dimensions are numeric approximations in the Sightline preview.")
    return CS2Import(validate_settings(settings), detected, list(dict.fromkeys(warnings)))


def export_cs2_commands(settings: Crosshair | dict[str, Any]) -> tuple[str, list[str]]:
    current = validate_settings(settings)
    red, green, blue = (int(current.color[index:index + 2], 16) for index in (1, 3, 5))
    warnings: list[str] = []
    if current.vertical_size != current.size:
        warnings.append("CS2 uses one arm length; Sightline horizontal length was exported for both axes.")
    if current.shape == "Circle":
        warnings.append("CS2 has no circle crosshair; the export uses a standard crosshair approximation.")
    if current.dot_size != Crosshair().dot_size:
        warnings.append("CS2 does not expose Sightline's independent center-dot size; the exported dot uses the game's size.")
    if current.shape not in {"Cross", "Dot", "T"}:
        warnings.append("The selected shape is approximated in CS2.")
    if current.opacity == 0:
        warnings.append("A fully transparent crosshair may not be visible in CS2.")
    if current.glow_enabled and current.shape != "Image":
        warnings.append("CS2 does not support Sightline's neon glow; the glow was not exported.")
    if current.outline > 0 and current.outline_color.upper() != Crosshair().outline_color.upper():
        warnings.append("CS2 does not let you choose the outline color; its exports always use the game's dark outline.")
    if current.offset_x or current.offset_y:
        warnings.append("CS2 always centers its crosshair; the Sightline screen offset was not exported.")
    warnings.append("CS2 game rendering and Sightline preview pixels are not identical; check the result in-game.")
    commands = [
        "cl_crosshairstyle 4",
        f"cl_crosshairsize {current.size}",
        f"cl_crosshairgap {current.gap}",
        f"cl_crosshairthickness {current.thickness}",
        f"cl_crosshair_drawoutline {int(current.outline > 0)}",
        f"cl_crosshair_outlinethickness {current.outline}",
        f"cl_crosshairdot {int(current.shape == 'Dot' or current.center_dot)}",
        f"cl_crosshair_t {int(current.shape == 'T')}",
        f"cl_crosshairalpha {round(current.opacity * 255 / 100)}",
        "cl_crosshaircolor 5",
        f"cl_crosshaircolor_r {red}",
        f"cl_crosshaircolor_g {green}",
        f"cl_crosshaircolor_b {blue}",
    ]
    return "\n".join(commands), warnings

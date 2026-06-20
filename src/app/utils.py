import os
import secrets
from PIL import Image
from pathlib import Path
import configparser
import json
import shutil
from PIL import Image, ExifTags
import pillow_heif

# Register HEIF opener
pillow_heif.register_heif_opener()

# Configuration constants
PHOTO_ROOT = '/app/photos'
THUMB_ROOT = '/app/thumbnails'
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic'}
IGNORED_DIRS = {'@eaDir', '#recycle', '#snapshot'}
THUMB_SIZE = (600, 600)

def is_image_file(filename):
    """Check if the file is an allowed image format."""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def get_album_cover(full_path):
    """
    Finds a cover image for the directory.
    Prioritizes '.ea_config.ini' setting, then 'cover.*' files, then falls back to the first image found.
    """
    try:
        # Check .ea_config.ini
        config_path = os.path.join(full_path, '.ea_config.ini')
        if os.path.exists(config_path):
            config = configparser.ConfigParser()
            config.read(config_path)
            if 'Album' in config and 'cover' in config['Album']:
                cover_img = config['Album']['cover']
                # Verify the file actually exists
                if os.path.exists(os.path.join(full_path, cover_img)):
                    return cover_img

        # Check for explicit cover image
        for entry in os.scandir(full_path):
            if entry.is_file() and entry.name.startswith('cover.') and is_image_file(entry.name):
                return entry.name
        
        # Fallback to first image
        for entry in os.scandir(full_path):
            if entry.is_file() and is_image_file(entry.name) and not entry.name.startswith('.'):
                return entry.name
    except OSError:
        pass
    return None

def set_album_cover(subpath, filename):
    """
    Sets the album cover in .ea_config.ini
    """
    full_dir = os.path.join(PHOTO_ROOT, subpath)
    if not os.path.exists(full_dir):
        return False, "Directory not found"
        
    full_img_path = os.path.join(full_dir, filename)
    if not os.path.exists(full_img_path):
        return False, "Image not found"
        
    config_path = os.path.join(full_dir, '.ea_config.ini')
    config = configparser.ConfigParser()
    
    if os.path.exists(config_path):
        config.read(config_path)
    
    if 'Album' not in config:
        config['Album'] = {}
        
    config['Album']['cover'] = filename
    
    try:
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        return True, "Cover updated"
    except Exception as e:
        return False, str(e)

def get_album_sort_config(full_path):
    """
    Reads the sort configuration from .ea_config.ini.
    Returns (sort_by, sort_order). Default is ('date', 'asc').
    """
    # 預設為拍攝日期升序
    sort_by = 'date'
    sort_order = 'asc'
    try:
        config_path = os.path.join(full_path, '.ea_config.ini')
        if os.path.exists(config_path):
            config = configparser.ConfigParser()
            config.read(config_path)
            if 'Sort' in config:
                sort_by = config['Sort'].get('by', 'date')
                sort_order = config['Sort'].get('order', 'asc')
    except Exception:
        pass
    
    if sort_by not in ['name', 'date']:
        sort_by = 'date'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'
        
    return sort_by, sort_order

def set_album_sort_config(subpath, sort_by, sort_order):
    """
    Sets the album sort configuration in .ea_config.ini
    """
    full_dir = os.path.join(PHOTO_ROOT, subpath)
    if not os.path.exists(full_dir):
        return False, "Directory not found"
        
    config_path = os.path.join(full_dir, '.ea_config.ini')
    config = configparser.ConfigParser()
    
    try:
        if os.path.exists(config_path):
            config.read(config_path)
        
        if 'Sort' not in config:
            config['Sort'] = {}
            
        config['Sort']['by'] = sort_by
        config['Sort']['order'] = sort_order
        
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        return True, "Sort config updated"
    except Exception as e:
        return False, str(e)

def get_album_share_token(subpath):
    """Get the sharing token for an album."""
    full_dir = os.path.join(PHOTO_ROOT, subpath)
    config_path = os.path.join(full_dir, '.ea_config.ini')
    if os.path.exists(config_path):
        config = configparser.ConfigParser()
        config.read(config_path)
        if 'Share' in config and 'token' in config['Share']:
            return config['Share']['token']
    return None

def set_album_share_token(subpath):
    """Generate and set a new sharing token for an album."""
    full_dir = os.path.join(PHOTO_ROOT, subpath)
    if not os.path.exists(full_dir):
        return None
    
    config_path = os.path.join(full_dir, '.ea_config.ini')
    config = configparser.ConfigParser()
    
    if os.path.exists(config_path):
        config.read(config_path)
        
    if 'Share' not in config:
        config['Share'] = {}
        
    token = secrets.token_urlsafe(16)
    config['Share']['token'] = token
    
    try:
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        return token
    except:
        return None

def verify_album_share_token(subpath, token):
    """Verify if the token matches the one stored for the album."""
    stored_token = get_album_share_token(subpath)
    return stored_token is not None and stored_token == token

def get_image_exif(file_path):
    """
    Extracts basic EXIF data from an image.
    Returns a dictionary or None.
    """
    try:
        img = Image.open(file_path)
        exif = img._getexif()
        exif_data = {}
        
        # Get file size
        try:
            size_bytes = os.path.getsize(file_path)
            if size_bytes >= 1024 * 1024:
                exif_data['size'] = f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                exif_data['size'] = f"{size_bytes / 1024:.0f} KB"
        except:
            pass

        if exif:
            for tag, value in exif.items():
                decoded = ExifTags.TAGS.get(tag, tag)
                if decoded == 'Model':
                    exif_data['model'] = str(value).strip()
                elif decoded == 'DateTimeOriginal':
                    date_str = str(value).strip()
                    if len(date_str) >= 16:
                        exif_data['date'] = date_str[:16].replace(':', '/', 2)
                    else:
                        exif_data['date'] = date_str
                elif decoded == 'FNumber':
                    try:
                        f_val = float(value)
                        exif_data['f_number'] = f"F{f_val:.1f}"
                    except:
                        exif_data['f_number'] = str(value)
                elif decoded == 'ExposureTime':
                    try:
                        val = float(value)
                        if val >= 1:
                            exif_data['shutter'] = f"{int(round(val))}s"
                        else:
                            denominator = int(round(1/val))
                            exif_data['shutter'] = f"1/{denominator}s"
                    except:
                        exif_data['shutter'] = str(value)
                elif decoded == 'ISOSpeedRatings':
                    try:
                        exif_data['iso'] = f"{int(value)}"
                    except:
                        exif_data['iso'] = f"{value}"
                elif decoded == 'LensModel' or tag == 42036:
                    exif_data['lens'] = str(value).strip()
                elif decoded == 'FocalLength':
                    try:
                        focal_val = float(value)
                        exif_data['focal_length'] = f"{focal_val:.0f}mm"
                    except:
                        exif_data['focal_length'] = str(value)
                elif decoded == 'Flash':
                    try:
                        flash_val = int(value)
                        if flash_val & 1:
                            exif_data['flash'] = "已閃光"
                        else:
                            exif_data['flash'] = "未閃光"
                    except:
                        exif_data['flash'] = str(value)
            
            # Extract readable raw exif for modal display
            raw_exif = {}
            for tag, value in exif.items():
                decoded = ExifTags.TAGS.get(tag, tag)
                if isinstance(decoded, str) and decoded not in ('MakerNote', 'UserComment', 'PrintImageMatching', 'ComponentsConfiguration'):
                    if isinstance(value, bytes):
                        continue
                    try:
                        val_str = str(value).strip()
                        if val_str and len(val_str) < 150:
                            raw_exif[decoded] = val_str
                    except:
                        pass
            exif_data['raw_exif'] = raw_exif
                
        keys = ['model', 'date', 'f_number', 'shutter', 'iso', 'lens', 'size', 'focal_length', 'flash', 'raw_exif']
        return {k: exif_data[k] for k in keys if k in exif_data}
    except Exception as e:
        return None

def load_exif_cache(folder_path):
    cache_path = os.path.join(folder_path, '.ea_exif.json')
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_exif_cache(folder_path, data):
    cache_path = os.path.join(folder_path, '.ea_exif.json')
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def clean_directory_cache(subpath):
    """
    Clears the thumbnail cache and EXIF cache for a specific directory.
    """
    if '..' in subpath: return False 
    
    thumb_dir = os.path.join(THUMB_ROOT, subpath)
    if os.path.exists(thumb_dir):
        try:
            shutil.rmtree(thumb_dir)
        except Exception as e:
            print(f"Error removing thumbs: {e}")
            
    full_path = os.path.join(PHOTO_ROOT, subpath)
    cache_path = os.path.join(full_path, '.ea_exif.json')
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
        except Exception as e:
            print(f"Error removing exif cache: {e}")
            
    return True

def scan_directory(subpath=''):
    """
    Scans a directory for folders and images.
    Returns a dictionary with 'dirs' and 'images'.
    """
    if '..' in subpath:
        return None
    
    full_path = os.path.join(PHOTO_ROOT, subpath)
    if not os.path.exists(full_path):
        return None

    items = {'dirs': [], 'images': []}
    exif_cache = load_exif_cache(full_path)
    cache_updated = False
    
    try:
        with os.scandir(full_path) as entries:
            for entry in entries:
                if entry.name.startswith('.') or entry.name in IGNORED_DIRS:
                    continue
                
                if entry.is_dir():
                    cover = get_album_cover(entry.path)
                    items['dirs'].append({'name': entry.name, 'cover': cover})
                elif entry.is_file() and is_image_file(entry.name):
                    exif_data = exif_cache.get(entry.name)
                    if exif_data is None:
                        exif_data = get_image_exif(entry.path)
                        exif_cache[entry.name] = exif_data
                        cache_updated = True
                        
                    items['images'].append({'name': entry.name, 'exif': exif_data})
        
        if cache_updated:
            save_exif_cache(full_path, exif_cache)
        
        sort_by, sort_order = get_album_sort_config(full_path)
        items['sort'] = {'by': sort_by, 'order': sort_order}

        items['dirs'].sort(key=lambda x: x['name'], reverse=True)
        
        reverse = (sort_order == 'desc')
        if sort_by == 'name':
            items['images'].sort(key=lambda x: x['name'].lower(), reverse=reverse)
        else:
            def get_date_key(img):
                try:
                    if img.get('exif') and img['exif'].get('date'):
                        return img['exif']['date']
                except Exception:
                    pass
                return "0000/00/00 00:00" if reverse else "9999/99/99 99:99"
            
            items['images'].sort(key=get_date_key, reverse=reverse)
        
    except PermissionError:
        print(f"Permission denied accessing {full_path}")
        return None
        
    return items

VISITOR_CONFIG_FILE = '.ea_visitor.json'

def get_visitor_albums():
    """Get the list of top-level albums accessible in visitor mode."""
    config_path = os.path.join(PHOTO_ROOT, VISITOR_CONFIG_FILE)
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('allowed_albums', [])
        except Exception:
            pass
    return []

def set_visitor_albums(album_list):
    """Set the list of top-level albums accessible in visitor mode."""
    config_path = os.path.join(PHOTO_ROOT, VISITOR_CONFIG_FILE)
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump({'allowed_albums': album_list}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving visitor config: {e}")
        return False

def is_visitor_accessible(subpath, allowed_albums):
    """Check if a subpath is accessible in visitor mode (based on top-level directory)."""
    if not subpath:
        return True
    first_component = subpath.strip('/').split('/')[0]
    return first_component in allowed_albums

def _is_safe_name(name):
    """Validate a single path component (a folder or file name)."""
    if not name:
        return False
    name = name.strip()
    if not name:
        return False
    if '/' in name or '\\' in name or '..' in name:
        return False
    if name.startswith('.'):
        return False
    return True

def create_album(parent_subpath, name):
    """Create a new sub-album (directory) named `name` inside parent_subpath."""
    if '..' in parent_subpath:
        return False, "Invalid path"

    name = (name or '').strip()
    if not _is_safe_name(name):
        return False, "相簿名稱不合法"

    parent_dir = os.path.join(PHOTO_ROOT, parent_subpath)
    if not os.path.isdir(parent_dir):
        return False, "Parent directory not found"

    new_dir = os.path.join(parent_dir, name)
    if os.path.exists(new_dir):
        return False, "同名相簿已存在"

    try:
        os.makedirs(new_dir)
        return True, name
    except Exception as e:
        return False, str(e)

def rename_album(subpath, new_name):
    """Rename an album directory and move its thumbnail cache."""
    if not subpath or '..' in subpath:
        return False, "Invalid path"

    new_name = (new_name or '').strip()
    if not _is_safe_name(new_name):
        return False, "相簿名稱不合法"

    old_dir = os.path.join(PHOTO_ROOT, subpath)
    if not os.path.isdir(old_dir):
        return False, "相簿不存在"

    parent_dir = os.path.dirname(old_dir)
    new_dir = os.path.join(parent_dir, new_name)
    if os.path.abspath(new_dir) == os.path.abspath(old_dir):
        return True, new_name
    if os.path.exists(new_dir):
        return False, "同名相簿已存在"

    try:
        os.rename(old_dir, new_dir)
    except Exception as e:
        return False, str(e)

    # Move the thumbnail cache so it stays in sync with the album
    old_thumb = os.path.join(THUMB_ROOT, subpath)
    if os.path.exists(old_thumb):
        new_thumb = os.path.join(os.path.dirname(old_thumb), new_name)
        try:
            if os.path.exists(new_thumb):
                shutil.rmtree(new_thumb)
            os.rename(old_thumb, new_thumb)
        except Exception as e:
            print(f"Error moving thumbnail cache: {e}")

    # Keep the visitor-accessible list in sync for top-level renames
    old_name = subpath.strip('/').split('/')[-1]
    if '/' not in subpath.strip('/'):
        allowed = get_visitor_albums()
        if old_name in allowed:
            allowed = [new_name if a == old_name else a for a in allowed]
            set_visitor_albums(allowed)

    return True, new_name

def delete_album(subpath):
    """Delete an album directory (and its contents) and its thumbnail cache."""
    if not subpath or '..' in subpath:
        return False, "Invalid path"

    target_dir = os.path.join(PHOTO_ROOT, subpath)
    if not os.path.isdir(target_dir):
        return False, "相簿不存在"

    try:
        shutil.rmtree(target_dir)
    except Exception as e:
        return False, str(e)

    # Remove the thumbnail cache as well
    thumb_dir = os.path.join(THUMB_ROOT, subpath)
    if os.path.exists(thumb_dir):
        try:
            shutil.rmtree(thumb_dir)
        except Exception as e:
            print(f"Error removing thumbnail cache: {e}")

    # Keep the visitor-accessible list in sync for top-level deletes
    name = subpath.strip('/').split('/')[-1]
    if '/' not in subpath.strip('/'):
        allowed = get_visitor_albums()
        if name in allowed:
            set_visitor_albums([a for a in allowed if a != name])

    return True, name

def save_uploaded_photos(subpath, files):
    """Save uploaded image files into the album directory.

    Returns (saved_count, errors_list).
    """
    if '..' in subpath:
        return 0, ["Invalid path"]

    target_dir = os.path.join(PHOTO_ROOT, subpath)
    if not os.path.isdir(target_dir):
        return 0, ["相簿不存在"]

    saved = 0
    errors = []
    for f in files:
        raw_name = (f.filename or '').replace('\\', '/').split('/')[-1]
        if not raw_name:
            continue
        if raw_name.startswith('.') or not is_image_file(raw_name):
            errors.append(f"{raw_name}: 非支援的圖片格式")
            continue

        # Avoid overwriting existing files by adding a numeric suffix
        dest = os.path.join(target_dir, raw_name)
        base, ext = os.path.splitext(raw_name)
        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(target_dir, f"{base}_{counter}{ext}")
            counter += 1

        try:
            f.save(dest)
            saved += 1
        except Exception as e:
            errors.append(f"{raw_name}: {e}")

    return saved, errors

def ensure_thumbnail(rel_path):
    """
    Ensures a thumbnail exists for the given image path (relative to PHOTO_ROOT).
    Returns the path to the thumbnail file (relative to THUMB_ROOT) or None on failure.
    """
    if '..' in rel_path:
        return None

    original_path = os.path.join(PHOTO_ROOT, rel_path)
    thumb_path = os.path.join(THUMB_ROOT, rel_path)
    
    if os.path.exists(thumb_path):
        try:
            if os.path.getmtime(thumb_path) >= os.path.getmtime(original_path):
                return thumb_path
        except OSError:
            pass

    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    
    try:
        with Image.open(original_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
                
            img.thumbnail(THUMB_SIZE)
            img.save(thumb_path, "JPEG", quality=95, optimize=True)
            return thumb_path
    except Exception as e:
        print(f"Error generating thumbnail for {rel_path}: {e}")
        return None

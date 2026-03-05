import os
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

def get_image_exif(file_path):
    """
    Extracts basic EXIF data from an image.
    Returns a dictionary or None.
    """
    try:
        img = Image.open(file_path)
        exif = img._getexif()
        if not exif:
            # Even if no EXIF, we might want size? 
            # But the function structure returns None if no EXIF. 
            # The user wants "exif info area" to show size.
            # If no EXIF, index.html doesn't show the block.
            # So we should probably initialize exif_data and keys even if img._getexif() is None?
            # But current logic returns None. 
            # Let's stick to current logic: if no EXIF, no display. 
            # Wait, `img._getexif()` returning None means no metadata.
            # But modern phones/cameras usually have it.
            # If I want to show size even for non-EXIF images, I need to change the return None to return empty dict with size.
            # But `index.html` checks `{% if img.exif %}`. 
            # So if I return `{'size': '...'}` it will display!
            # So I should handle the `if not exif:` block better or just initialize `exif_data` earlier.
            pass

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
                    # Convert YYYY:MM:DD HH:MM:SS to YYYY/MM/DD HH:MM
                    date_str = str(value).strip()
                    if len(date_str) >= 16:
                        exif_data['date'] = date_str[:16].replace(':', '/', 2)
                    else:
                        exif_data['date'] = date_str
                elif decoded == 'FNumber':
                    # F-Number to 1 decimal place
                    try:
                        f_val = float(value)
                        exif_data['f_number'] = f"F{f_val:.1f}"
                    except:
                        exif_data['f_number'] = str(value)
                elif decoded == 'ExposureTime':
                    # Shutter speed formatting
                    try:
                        val = float(value)
                        if val >= 1:
                            # >= 1s: integer
                            exif_data['shutter'] = f"{int(round(val))}s"
                        else:
                            # < 1s: fraction with integer denominator, e.g. 1/200
                            denominator = int(round(1/val))
                            exif_data['shutter'] = f"1/{denominator}s"
                    except:
                        exif_data['shutter'] = str(value)
                elif decoded == 'ISOSpeedRatings':
                    # ISO: integer
                    try:
                        exif_data['iso'] = f"{int(value)}"
                    except:
                        exif_data['iso'] = f"{value}"
                elif decoded == 'LensModel' or tag == 42036:
                    exif_data['lens'] = str(value).strip()
                
        # Filter for only keys we care about
        keys = ['model', 'date', 'f_number', 'shutter', 'iso', 'lens', 'size']
        return {k: exif_data[k] for k in keys if k in exif_data}
    except Exception as e:
        # print(f"Error reading EXIF for {file_path}: {e}")
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
    # 1. Clear thumbnails
    if '..' in subpath: return False # Safety check
    
    thumb_dir = os.path.join(THUMB_ROOT, subpath)
    if os.path.exists(thumb_dir):
        try:
            shutil.rmtree(thumb_dir)
        except Exception as e:
            print(f"Error removing thumbs: {e}")
            
    # 2. Clear EXIF cache
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
    # Prevent directory traversal
    if '..' in subpath:
        return None
    
    full_path = os.path.join(PHOTO_ROOT, subpath)
    if not os.path.exists(full_path):
        return None

    items = {'dirs': [], 'images': []}
    
    # Load EXIF cache
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
                    # Check cache for EXIF
                    exif_data = exif_cache.get(entry.name)
                    if exif_data is None:
                        # Cache miss, generate
                        exif_data = get_image_exif(entry.path)
                        exif_cache[entry.name] = exif_data
                        cache_updated = True
                        
                    items['images'].append({'name': entry.name, 'exif': exif_data})
        
        # Save cache if updated
        if cache_updated:
            save_exif_cache(full_path, exif_cache)
        
        # 取得排序設定
        sort_by, sort_order = get_album_sort_config(full_path)
        items['sort'] = {'by': sort_by, 'order': sort_order}

        # 資料夾永遠依照名稱排序
        items['dirs'].sort(key=lambda x: x['name'])
        
        # 圖片依照設定進行排序
        reverse = (sort_order == 'desc')
        if sort_by == 'name':
            items['images'].sort(key=lambda x: x['name'].lower(), reverse=reverse)
        else: # sort_by == 'date'
            def get_date_key(img):
                try:
                    if img.get('exif') and img['exif'].get('date'):
                        return img['exif']['date']
                except Exception:
                    pass
                # 缺乏日期時，升降序給予極值補墊排至尾端
                return "0000/00/00 00:00" if reverse else "9999/99/99 99:99"
            
            items['images'].sort(key=get_date_key, reverse=reverse)
        
    except PermissionError:
        print(f"Permission denied accessing {full_path}")
        return None
        
    return items

def ensure_thumbnail(rel_path):
    """
    Ensures a thumbnail exists for the given image path (relative to PHOTO_ROOT).
    Returns the path to the thumbnail file (relative to THUMB_ROOT) or None on failure.
    """
    if '..' in rel_path:
        return None

    original_path = os.path.join(PHOTO_ROOT, rel_path)
    thumb_path = os.path.join(THUMB_ROOT, rel_path)
    
    # Check if thumbnail already exists and is newer than original
    if os.path.exists(thumb_path):
        try:
            if os.path.getmtime(thumb_path) >= os.path.getmtime(original_path):
                return thumb_path
        except OSError:
            pass # Force regeneration if stats fail

    # Create directory for thumbnail if it doesn't exist
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    
    try:
        with Image.open(original_path) as img:
            # Convert to RGB if necessary (e.g. for RGBA/P images saving as JPEG)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
                
            img.thumbnail(THUMB_SIZE)
            img.save(thumb_path, "JPEG", quality=95, optimize=True)
            return thumb_path
    except Exception as e:
        print(f"Error generating thumbnail for {rel_path}: {e}")
        return None

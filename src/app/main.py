import os
import io
from urllib.parse import quote
from PIL import Image
from flask import Flask, render_template, send_from_directory, abort, request, jsonify, send_file, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from src.app.utils import scan_directory, ensure_thumbnail, set_album_cover, set_album_sort_config, clean_directory_cache, PHOTO_ROOT, THUMB_ROOT, get_album_share_token, set_album_share_token, verify_album_share_token, get_album_cover

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-please-change')

# Login Manager Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Admin User Configuration
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id == ADMIN_USERNAME:
        return User(user_id)
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            user = User(username)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Basic landing page - redirects to album root
@app.route('/')
@login_required
def index():
    return album_view('')

@app.route('/album/')
@app.route('/album/<path:subpath>')
@login_required
def album_view(subpath=''):
    """Display the contents of a directory (sub-albums and photos)."""
    content = scan_directory(subpath)
    if content is None:
        abort(404, description="Album not found or access denied")
        
    # Breadcrumbs construction
    breadcrumbs = []
    parts = subpath.strip('/').split('/')
    if parts == ['']:
        parts = []
    
    current_path = ''
    for part in parts:
        current_path = os.path.join(current_path, part)
        breadcrumbs.append({'name': part, 'path': current_path})

    return render_template('index.html', 
                         subpath=subpath, 
                         dirs=content['dirs'], 
                         images=content['images'],
                         sort=content.get('sort'),
                         breadcrumbs=breadcrumbs)

@app.route('/river/')
@app.route('/river/<path:subpath>')
def river_view(subpath=''):
    """Display the photos in Flickriver style (read-only, vertical scroll)."""
    token = request.args.get('token')
    is_public = False
    
    if token:
        if verify_album_share_token(subpath, token):
            is_public = True
        else:
            abort(403, description="Invalid sharing token")
    
    if not is_public and not current_user.is_authenticated:
        return redirect(url_for('login'))
        
    content = scan_directory(subpath)
    if content is None:
        abort(404, description="Album not found or access denied")

    # 取得封面圖用於 OG image
    cover_url = None
    full_dir = os.path.join(PHOTO_ROOT, subpath)
    cover_filename = get_album_cover(full_dir)
    if cover_filename:
        base_url = request.host_url.rstrip('/')
        encoded_cover_path = quote(
            (subpath + '/' + cover_filename).lstrip('/'), safe='/'
        )
        cover_url = f"{base_url}/thumbnail/{encoded_cover_path}"

    return render_template('river.html', 
                         subpath=subpath, 
                         images=content['images'],
                         is_public=is_public,
                         cover_url=cover_url)

@app.route('/api/share-link', methods=['POST'])
@login_required
def share_link():
    """API to generate or get a sharing link for an album."""
    data = request.get_json()
    if not data or 'subpath' not in data:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400
        
    subpath = data['subpath']
    token = get_album_share_token(subpath)
    
    if not token:
        token = set_album_share_token(subpath)
        
    if token:
        # Construct full URL
        base_url = request.host_url.rstrip('/')
        encoded_path = quote(subpath, safe='/')
        share_url = f"{base_url}/river/{encoded_path}?token={token}"
        return jsonify({'success': True, 'share_url': share_url})
    else:
        return jsonify({'success': False, 'error': 'Failed to generate token'}), 500

@app.route('/api/set-sort', methods=['POST'])
@login_required
def set_sort():
    """API to set the sorting method for an album."""
    data = request.get_json()
    if not data or 'subpath' not in data or 'sort_by' not in data or 'sort_order' not in data:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400
        
    subpath = data['subpath']
    sort_by = data['sort_by']
    sort_order = data['sort_order']
    
    if sort_by not in ['name', 'date'] or sort_order not in ['asc', 'desc']:
        return jsonify({'success': False, 'error': 'Invalid sort parameters'}), 400
        
    success, message = set_album_sort_config(subpath, sort_by, sort_order)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': message}), 500

@app.route('/api/set-cover', methods=['POST'])
@login_required
def set_cover():
    """API to set the cover image for an album."""
    data = request.get_json()
    if not data or 'subpath' not in data or 'filename' not in data:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400
        
    subpath = data['subpath']
    filename = data['filename']
    
    success, message = set_album_cover(subpath, filename)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': message}), 500

@app.route('/api/regenerate', methods=['POST'])
@login_required
def regenerate():
    """API to clear cache and regenerate thumbnails/EXIF."""
    data = request.get_json()
    if not data:
        subpath = ''
    else:
        subpath = data.get('subpath', '')
        
    if '..' in subpath:
         return jsonify({'success': False, 'error': 'Invalid path'}), 400
         
    success = clean_directory_cache(subpath)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to clean cache'}), 500

@app.route('/thumbnail/<path:filename>')
def serve_thumbnail(filename):
    """Serve a thumbnail, generating it if necessary."""
    thumb_path = ensure_thumbnail(filename)
    
    if thumb_path:
        if filename.lower().endswith('.heic'):
             if os.path.exists(thumb_path):
                 return send_from_directory(THUMB_ROOT, filename, mimetype='image/jpeg')

        if os.path.exists(thumb_path):
             return send_from_directory(THUMB_ROOT, filename)
             
    abort(404)

@app.route('/photo/<path:filename>')  
def serve_photo(filename):
    """Serve the original photo."""
    if filename.lower().endswith('.heic'):
        full_path = os.path.join(PHOTO_ROOT, filename)
        if not os.path.exists(full_path):
             abort(404)
        try:
            img = Image.open(full_path)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
                
            img_io = io.BytesIO()
            img.save(img_io, 'JPEG', quality=95)
            img_io.seek(0)
            return send_file(img_io, mimetype='image/jpeg')
        except Exception as e:
            print(f"Error converting HEIC: {e}")
            abort(500)
            
    return send_from_directory(PHOTO_ROOT, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)

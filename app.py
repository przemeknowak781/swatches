import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import numpy as np
import io
import zipfile
import base64
import sys # Keep for potential future use
import os
import time
import requests # For URL image fetching

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("SwatchBatch - Advanced Color Palette Generator")

# --- Initialize Session State ---
if 'generation_stage' not in st.session_state:
    st.session_state.generation_stage = "initial" # Stages: "initial", "preview_generated", "full_batch_generating", "completed"
if 'preview_html_parts' not in st.session_state:
    st.session_state.preview_html_parts = []
if 'generated_image_data' not in st.session_state:
    st.session_state.generated_image_data = {}
if 'zip_buffer' not in st.session_state:
    st.session_state.zip_buffer = None
if 'total_generations_at_start' not in st.session_state:
    st.session_state.total_generations_at_start = 0
if 'current_settings_hash' not in st.session_state:
    st.session_state.current_settings_hash = None
if 'full_batch_button_clicked' not in st.session_state:
    st.session_state.full_batch_button_clicked = False
if 'image_url_input_key' not in st.session_state: 
    st.session_state.image_url_input_key = "image_url_input_0"
if 'file_uploader_key' not in st.session_state: 
    st.session_state.file_uploader_key = "file_uploader_0"


# --- Global containers for dynamic content ---
spinner_container = st.empty()
preview_container = st.container()
download_buttons_container = st.container()
preloader_and_status_container = st.empty()
generate_full_batch_button_container = st.empty()


# --- CSS for responsive columns and general styling ---
st.markdown("""
    <style>
    @media (min-width: 768px) {
        .responsive-columns {
            display: flex;
            gap: 2rem; /* Gap between the main three columns */
        }
        .responsive-columns > div {
            flex: 1;
        }
    }

    #preview-zone {
        display: flex;
        flex-wrap: nowrap; 
        overflow-x: auto; 
        gap: 20px;        
        padding: 20px;    
        border-radius: 8px;
        min-height: 250px; 
        align-items: flex-start; 
        margin-bottom: 20px; 
        background: #ffffff; 
        border: 1px solid #e0e0e0; 
    }

    .preview-item {
        flex: 0 0 auto; 
        display: flex; 
        flex-direction: column; 
        align-items: center; 
        text-align: center;
        width: 220px; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.15); 
        padding: 10px; 
        border-radius: 8px;
        background: #f0f0f0; 
        border: 1px solid #e0e0e0;
    }

    .preview-item img {
        width: 100%; 
        height: auto;     
        border-radius: 4px; 
        margin-bottom: 8px; 
        object-fit: contain; 
        max-height: 180px; 
    }

    .preview-item-name {
        font-size: 12px;
        margin-bottom: 5px;
        color: #333;
        word-break: break-all; 
        height: 30px; 
        overflow: hidden;
        width: 100%; 
        text-overflow: ellipsis; 
        white-space: nowrap; 
    }

    .download-link {
        font-size: 10px;
        color: #888; 
        text-decoration: none; 
        margin-top: 5px; 
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%; 
        display: block; 
    }

    .download-link:hover {
        text-decoration: underline; 
        color: #555;
    }

    h2 {
        margin-bottom: 0.9rem !important;
    }

    .stDownloadButton {
        margin-top: 10px;
    }
    /* Ensure download buttons take full width if desired */
    .stDownloadButton button {
        width: 100%;
    }


    .preloader-area {
        display: flex;
        align-items: center;
        justify-content: center; 
        margin: 20px auto; 
        min-height: 40px; 
    }

    .preloader {
        border: 4px solid #f3f3f3; 
        border-top: 4px solid #3498db; 
        border-radius: 50%;
        width: 30px;
        height: 30px;
        animation: spin 1s linear infinite;
        margin-right: 15px; 
    }

    .preloader-text {
        font-size: 16px;
        color: #555;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    /* Custom style for the blue "Large batch detected..." button */
    /* This targets Streamlit's secondary button type */
    div[data-testid="stButton"] > button[type="button"].st-emotion-cache- LcTzUn.e1nzilvr2 {
        background-color: #007BFF !important; 
        color: white !important; 
        border-color: #007BFF !important; 
    }
    /* Fallback or alternative if class name changes, targeting by kind attribute if possible */
     div[data-testid="stButton"] > button[kind="secondary"] {
        background-color: #007BFF !important;
        color: white !important;
        border-color: #007BFF !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- Utility Functions ---

def shorten_filename(filename, max_len=25, front_chars=10, back_chars=10):
    """Shortens a filename to fit max_len, keeping front_chars and back_chars."""
    if len(filename) > max_len:
        name, ext = os.path.splitext(filename)
        back_chars_name = max(0, back_chars - len(ext))
        return f"{name[:front_chars]}...{name[-back_chars_name:]}{ext}"
    return filename

def is_valid_image_header(file_bytes):
    """Checks image format magic bytes. Returns format string or None."""
    header = file_bytes[:12]
    if header.startswith(b'\xFF\xD8\xFF'): return 'jpeg'
    if header.startswith(b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A'): return 'png'
    if header.startswith(b'\x47\x49\x46\x38\x37\x61') or header.startswith(b'\x47\x49\x46\x38\x39\x61'): return 'gif'
    if header.startswith(b'\x42\x4D'): return 'bmp'
    if header.startswith(b'\x49\x49\x2A\x00') or header.startswith(b'\x4D\x4D\x00\x2A'): return 'tiff'
    if header.startswith(b'\x52\x49\x46\x46') and header[8:12] == b'\x57\x45\x42\x50': return 'webp'
    if header.startswith(b'\x00\x00\x01\x00') or header.startswith(b'\x00\x00\x02\x00'): return 'ico'
    return None

# --- Color Extraction ---

def extract_palette(image, num_colors=6, quantize_method=Image.MEDIANCUT):
    """Extracts a color palette from the image."""
    img = image.convert("RGB")
    try:
        paletted = img.quantize(colors=num_colors, method=quantize_method, kmeans=5)
        palette_full = paletted.getpalette()
        if palette_full is None: # Fallback if getpalette returns None
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE, kmeans=5) # Try FASTOCTREE
            palette_full = paletted.getpalette()
            if palette_full is None: return [] # Still None, return empty
        
        actual_palette_colors = len(palette_full) // 3
        colors_to_extract = min(num_colors, actual_palette_colors)
        extracted_palette_rgb_values = palette_full[:colors_to_extract * 3]
        return [tuple(extracted_palette_rgb_values[i:i+3]) for i in range(0, len(extracted_palette_rgb_values), 3)]
    except Exception: # Broad exception for primary method
        try: # Fallback to FASTOCTREE if primary fails
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE, kmeans=5)
            palette = paletted.getpalette()
            if palette is None: return []
            return [tuple(palette[i:i+3]) for i in range(0, min(num_colors * 3, len(palette)), 3)]
        except Exception: # If fallback also fails
            return []

# --- Draw Layout Function ---

def draw_layout(image, colors, position, 
                image_border_percent, swatch_separator_percent, individual_swatch_border_percent,
                border_color, swatch_border_color, swatch_size_percent_of_shorter_dim):
    """Draws the image layout with color swatches.
    All border/line thicknesses and swatch size are based on percentages of the image's shorter dimension.
    """
    img_w, img_h = image.size
    shorter_dimension = min(img_w, img_h)

    # Calculate actual pixel thicknesses from percentages
    image_border_thickness_px = int(shorter_dimension * (image_border_percent / 100))
    swatch_separator_thickness_px = int(shorter_dimension * (swatch_separator_percent / 100))
    individual_swatch_border_thickness_px = int(shorter_dimension * (individual_swatch_border_percent / 100))

    # Ensure minimum 1px if percentage results in >0 but <1px, or handle 0px explicitly
    if image_border_percent > 0 and image_border_thickness_px == 0: image_border_thickness_px = 1
    if swatch_separator_percent > 0 and swatch_separator_thickness_px == 0: swatch_separator_thickness_px = 1
    if individual_swatch_border_percent > 0 and individual_swatch_border_thickness_px == 0: individual_swatch_border_thickness_px = 1
    
    main_border = image_border_thickness_px
    internal_swatch_border_thickness = individual_swatch_border_thickness_px

    # Calculate actual swatch size in pixels based on percentage of the shorter dimension
    actual_swatch_size_px = int(shorter_dimension * (swatch_size_percent_of_shorter_dim / 100))
    if actual_swatch_size_px <= 0 and swatch_size_percent_of_shorter_dim > 0 : actual_swatch_size_px = 1
    elif actual_swatch_size_px <= 0: actual_swatch_size_px = 0


    if not colors: # If no colors, just draw border if specified
        if main_border > 0:
            canvas = Image.new("RGB", (img_w + 2 * main_border, img_h + 2 * main_border), border_color)
            canvas.paste(image, (main_border, main_border))
            return canvas
        return image.copy() # Return original if no colors and no border

    # Initialize variables for swatch dimensions and positions
    swatch_width = 0
    swatch_height = 0
    extra_width_for_last_swatch = 0
    extra_height_for_last_swatch = 0
    # swatch_x_start, swatch_y_start, swatch_x, swatch_y initialized based on position
    image_paste_x = main_border
    image_paste_y = main_border

    # Determine canvas size and image paste position based on swatch position
    if position == 'top':
        canvas_h = img_h + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_w = img_w + 2 * main_border
        swatch_y_coord = main_border # Renamed from swatch_y to avoid conflict in draw.rectangle
        swatch_x_start = main_border
        swatch_total_width = img_w
        if len(colors) > 0:
            swatch_width = swatch_total_width // len(colors)
            extra_width_for_last_swatch = swatch_total_width % len(colors)
        image_paste_y = main_border + actual_swatch_size_px + swatch_separator_thickness_px
    elif position == 'bottom':
        canvas_h = img_h + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_w = img_w + 2 * main_border
        swatch_y_coord = main_border + img_h + swatch_separator_thickness_px
        swatch_x_start = main_border
        swatch_total_width = img_w
        if len(colors) > 0:
            swatch_width = swatch_total_width // len(colors)
            extra_width_for_last_swatch = swatch_total_width % len(colors)
        image_paste_y = main_border # Image is at the top
    elif position == 'left':
        canvas_w = img_w + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_h = img_h + 2 * main_border
        swatch_x_coord = main_border # Renamed from swatch_x
        swatch_y_start = main_border
        swatch_total_height = img_h
        if len(colors) > 0:
            swatch_height = swatch_total_height // len(colors)
            extra_height_for_last_swatch = swatch_total_height % len(colors)
        image_paste_x = main_border + actual_swatch_size_px + swatch_separator_thickness_px
    elif position == 'right':
        canvas_w = img_w + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_h = img_h + 2 * main_border
        swatch_x_coord = main_border + img_w + swatch_separator_thickness_px
        swatch_y_start = main_border
        swatch_total_height = img_h
        if len(colors) > 0:
            swatch_height = swatch_total_height // len(colors)
            extra_height_for_last_swatch = swatch_total_height % len(colors)
        image_paste_x = main_border # Image is on the left
    else: # Should not happen
        return image.copy()

    # Create canvas and paste image
    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    canvas.paste(image, (image_paste_x, image_paste_y))
    draw = ImageDraw.Draw(canvas)

    # Draw color swatches
    for i, color_tuple in enumerate(colors):
        current_swatch_width = swatch_width
        current_swatch_height = swatch_height
        
        # Define x0,y0,x1,y1 for the current swatch rectangle
        if position in ['top', 'bottom']:
            if i == len(colors) - 1: current_swatch_width += extra_width_for_last_swatch
            rect_x0 = swatch_x_start + i * swatch_width
            rect_x1 = rect_x0 + current_swatch_width
            rect_y0 = swatch_y_coord
            rect_y1 = swatch_y_coord + actual_swatch_size_px
        else: # 'left' or 'right'
            if i == len(colors) - 1: current_swatch_height += extra_height_for_last_swatch
            rect_y0 = swatch_y_start + i * swatch_height
            rect_y1 = rect_y0 + current_swatch_height
            rect_x0 = swatch_x_coord
            rect_x1 = swatch_x_coord + actual_swatch_size_px
        
        draw.rectangle([rect_x0, rect_y0, rect_x1, rect_y1], fill=tuple(color_tuple))

        # Draw internal borders between swatches
        if internal_swatch_border_thickness > 0 and i < len(colors) - 1:
            if position in ['top', 'bottom']:
                # Vertical line to the right of the current swatch
                draw.line([(rect_x1, rect_y0), (rect_x1, rect_y1)], fill=swatch_border_color, width=internal_swatch_border_thickness)
            else: # 'left' or 'right'
                # Horizontal line below the current swatch
                draw.line([(rect_x0, rect_y1), (rect_x1, rect_y1)], fill=swatch_border_color, width=internal_swatch_border_thickness)

    # Draw main border around the entire canvas
    if main_border > 0:
        draw.line([(0, 0), (canvas_w - 1, 0)], fill=border_color, width=main_border) # Top
        draw.line([(0, canvas_h - 1), (canvas_w - 1, canvas_h - 1)], fill=border_color, width=main_border) # Bottom
        draw.line([(0, 0), (0, canvas_h - 1)], fill=border_color, width=main_border) # Left
        draw.line([(canvas_w - 1, 0), (canvas_w - 1, canvas_h - 1)], fill=border_color, width=main_border) # Right

    # Draw border between swatch area and image
    if swatch_separator_thickness_px > 0 and actual_swatch_size_px > 0: # Only draw if swatches exist and separator is specified
        if position == 'top':
            line_y = main_border + actual_swatch_size_px
            draw.line([(main_border, line_y), (main_border + img_w, line_y)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'bottom':
            line_y = main_border + img_h # Line is above the bottom swatches
            draw.line([(main_border, line_y), (main_border + img_w, line_y)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'left':
            line_x = main_border + actual_swatch_size_px
            draw.line([(line_x, main_border), (line_x, main_border + img_h)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'right':
            line_x = main_border + img_w # Line is to the left of the right swatches
            draw.line([(line_x, main_border), (line_x, main_border + img_h)], fill=swatch_border_color, width=swatch_separator_thickness_px)
    return canvas


# --- Input Columns ---
col1, col2, col3 = st.columns(3)

# --- Top-level exception handling ---
try:
    with col1:
        st.subheader("Upload Images")
        
        # File uploader first
        allowed_extensions = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif", "ico"]
        uploaded_files_from_uploader = st.file_uploader(
            "Choose images from your device",
            accept_multiple_files=True,
            type=allowed_extensions,
            key=st.session_state.file_uploader_key
        )

        # URL input below file uploader
        image_url = st.text_input("Or enter image URL", key=st.session_state.image_url_input_key, placeholder="https://example.com/image.jpg")


        all_image_sources = [] # To store {'name': str, 'bytes': bytes, 'source_type': 'file'/'url', 'original_input': str}

        # Process uploaded files
        if uploaded_files_from_uploader:
            allowed_extensions_set = set([f".{ext.lower()}" for ext in allowed_extensions])
            for file_obj in uploaded_files_from_uploader:
                file_name = file_obj.name
                try:
                    file_obj.seek(0)
                    file_bytes_sample = file_obj.read(12) # Read first 12 bytes for header check
                    file_obj.seek(0) # Reset file pointer
                    detected_format_from_header = is_valid_image_header(file_bytes_sample)

                    if detected_format_from_header is None:
                        st.warning(f"File `{file_name}` does not appear to be a valid image based on its header. Skipped.")
                        continue
                    
                    file_extension_original = os.path.splitext(file_name)[1].lower()
                    # Warn if unusual extension, but proceed if header is valid
                    if file_extension_original not in allowed_extensions_set and file_extension_original : # Check if extension exists
                         st.warning(f"`{file_name}` has an unusual extension (`{file_extension_original}`). Processing based on detected header: '{detected_format_from_header}'.")

                    # Use detected format for consistent naming if different from original extension
                    # This helps if a .jpg is actually a png, etc.
                    # However, for user clarity, might be better to keep original name and rely on PIL to handle format.
                    # For now, let's keep the original name for the list, PIL will handle opening.
                    all_image_sources.append({'name': file_name, 
                                              'bytes': file_obj.getvalue(), 
                                              'source_type': 'file', 
                                              'original_input': file_name})
                except Exception as e:
                     st.error(f"Error processing uploaded file `{file_name}`: {e}. Skipped.")
                     continue

        # Process URL input
        if image_url: # If a URL is entered
            try:
                is_new_url = True
                # Check cache to avoid re-downloading if URL hasn't changed and was successfully processed
                for src in st.session_state.get('processed_sources_cache', []):
                    if src['original_input'] == image_url and src['source_type'] == 'url':
                        all_image_sources.append(src) # Use cached data
                        is_new_url = False
                        st.info(f"Using cached image from URL: {shorten_filename(src['name'])}")
                        break
                
                if is_new_url:
                    st.info(f"Fetching image from URL: {image_url}...")
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                    response = requests.get(image_url, timeout=15, headers=headers, stream=True) # stream=True for large files
                    response.raise_for_status() # Raise HTTPError for bad responses (4XX or 5XX)

                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > 20 * 1024 * 1024: # 20MB limit
                        st.error(f"Image from URL {image_url} is too large (>{int(content_length)/(1024*1024):.1f}MB). Max 20MB. Skipped.")
                    else:
                        image_bytes = response.content # Read the content
                        
                        # Try to infer a filename from URL
                        url_file_name_base = os.path.basename(image_url.split("?")[0].strip()) 
                        if not url_file_name_base or '.' not in url_file_name_base: # Basic check if it looks like a filename
                             url_file_name_base = "image_from_url" # Default name if cannot infer

                        detected_format = is_valid_image_header(image_bytes[:12])
                        if detected_format:
                            # Create a more robust filename using the detected format
                            name_part, _ = os.path.splitext(url_file_name_base)
                            final_url_file_name = f"{name_part}.{detected_format}"
                            
                            source_data = {'name': final_url_file_name, 
                                           'bytes': image_bytes, 
                                           'source_type': 'url', 
                                           'original_input': image_url} # Store original URL for caching key
                            all_image_sources.append(source_data)
                            
                            # Cache successful URL fetches
                            if 'processed_sources_cache' not in st.session_state:
                                st.session_state.processed_sources_cache = []
                            if not any(item['original_input'] == image_url for item in st.session_state.processed_sources_cache):
                                st.session_state.processed_sources_cache.append(source_data)
                            st.success(f"Fetched: {final_url_file_name}")
                        else:
                            st.warning(f"Could not validate image from URL: {image_url}. Content might not be a direct image link or is unsupported. Skipped.")
            except requests.exceptions.MissingSchema:
                st.error(f"Invalid URL: '{image_url}'. Please include http:// or https://.")
            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching from URL {image_url}: {e}.")
            except Exception as e: 
                st.error(f"Error processing URL {image_url}: {e}")
        
        # Attempt to clear URL input after processing to allow new entry (Streamlit trick)
        if image_url and (st.session_state.generation_stage == "initial" or st.session_state.generation_stage == "completed"):
             if any(src.get('original_input') == image_url and src.get('source_type') == 'url' for src in all_image_sources):
                st.session_state.image_url_input_key = f"image_url_input_{int(st.session_state.image_url_input_key.split('_')[-1]) + 1}"

        st.subheader("Output Options")
        output_format_options = ["JPG", "PNG", "WEBP"]
        output_format = st.selectbox("Output format", output_format_options, key="output_format")
        webp_lossless = False
        if output_format == "WEBP":
            webp_lossless = st.checkbox("Lossless WEBP", value=False, key="webp_lossless", help="Generates larger files, better quality.")
        format_map = {"JPG": ("JPEG", "jpg"), "PNG": ("PNG", "png"), "WEBP": ("WEBP", "webp")}
        img_format, extension = format_map[output_format]

    with col2:
        st.subheader("Layout Settings")
        positions = []
        st.write("Swatch position(s):")
        row1_layout, row2_layout = st.columns(2), st.columns(2)
        if row1_layout[0].toggle("Top", value=True, key="pos_top"): positions.append("top")
        if row1_layout[1].toggle("Left", value=True, key="pos_left"): positions.append("left")
        if row2_layout[0].toggle("Bottom", value=True, key="pos_bottom"): positions.append("bottom")
        if row2_layout[1].toggle("Right", key="pos_right"): positions.append("right")

        quant_method_label = st.selectbox("Palette extraction", ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"], 0, key="quant_method")
        quant_method_map = {"MEDIANCUT": Image.MEDIANCUT, "MAXCOVERAGE": Image.MAXCOVERAGE, "FASTOCTREE": Image.FASTOCTREE}
        quantize_method_selected = quant_method_map[quant_method_label]
        num_colors = st.slider("Number of swatches", 2, 12, 6, key="num_colors")
        
        swatch_size_percent_val = st.slider("Swatch size (% of shorter image dim.)", 0.0, 100.0, 20.0, step=0.5, key="swatch_size_percent", help="Swatch thickness as a percentage of the image's shorter dimension.")

    with col3:
        st.subheader("Borders (Lines)")
        image_border_thickness_percent_val = st.slider("Image Border (% of shorter dim.)", 0.0, 20.0, 0.0, step=0.1, key="image_border_thickness_percent")
        swatch_separator_thickness_percent_val = st.slider("Swatch-Image Separator (% of shorter dim.)", 0.0, 20.0, 0.0, step=0.1, key="swatch_separator_thickness_percent")
        individual_swatch_border_thickness_percent_val = st.slider("Individual Swatch Border (% of shorter dim.)", 0.0, 20.0, 0.0, step=0.1, key="individual_swatch_border_thickness_percent")
        
        border_color = st.color_picker("Main Border Color", "#FFFFFF", key="border_color")
        swatch_border_color = st.color_picker("Swatch Border Color", "#FFFFFF", key="swatch_border_color")

    # --- Check for settings change to reset state ---
    processed_sources_tuple = tuple(
        (src['name'], src['bytes'].__hash__(), src['source_type'], src.get('original_input')) for src in all_image_sources
    )
    current_settings = (
        processed_sources_tuple, 
        frozenset(positions),
        output_format, webp_lossless,
        quant_method_label, num_colors,
        swatch_size_percent_val,
        image_border_thickness_percent_val, 
        swatch_separator_thickness_percent_val, 
        individual_swatch_border_thickness_percent_val,
        border_color, swatch_border_color,
        # image_url # image_url itself is part of processed_sources_tuple via original_input
    )
    current_settings_hash = hash(current_settings)

    if st.session_state.current_settings_hash is not None and st.session_state.current_settings_hash != current_settings_hash:
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts = []
        st.session_state.generated_image_data = {}
        st.session_state.zip_buffer = None
        st.session_state.total_generations_at_start = 0
        st.session_state.full_batch_button_clicked = False
        generate_full_batch_button_container.empty()
        
        # More targeted cache clearing: if the actual sources changed, clear URL cache
        # This prevents clearing cache just for a slider change if sources are same.
        if 'previous_sources_tuple_for_cache_check' in st.session_state and \
           processed_sources_tuple != st.session_state.previous_sources_tuple_for_cache_check and \
           'processed_sources_cache' in st.session_state:
            del st.session_state.processed_sources_cache
            # st.info("Image sources changed, clearing URL cache.")


    st.session_state.current_settings_hash = current_settings_hash
    st.session_state.previous_sources_tuple_for_cache_check = processed_sources_tuple


    # --- Main Generation Logic ---
    if all_image_sources and positions:
        total_generations = len(all_image_sources) * len(positions)
        st.session_state.total_generations_at_start = total_generations

        st.markdown("---") # Visual separator
        preview_display_area = preview_container.empty()
        # Ensure preview zone is always defined for CSS, even if empty initially
        preview_display_area.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True) 

        images_to_process_this_run = []
        layouts_to_process = positions # All selected layouts
        
        # Determine if this run is for initial preview or full batch
        is_initial_preview_phase = (st.session_state.generation_stage == "initial" and total_generations > 10)
        is_full_batch_phase = (st.session_state.generation_stage == "full_batch_generating")
        is_small_batch_phase = (total_generations <= 10 and st.session_state.generation_stage == "initial") # Small batches generate all at once

        current_processing_limit = total_generations # Default to all

        if is_initial_preview_phase:
            images_to_process_this_run = all_image_sources[:6] # Max 6 images for preview
            current_processing_limit = len(images_to_process_this_run) * len(layouts_to_process)
        elif is_full_batch_phase or is_small_batch_phase:
            images_to_process_this_run = all_image_sources # All images
            # current_processing_limit remains total_generations
        
        # Condition to start or continue generation
        should_generate_now = is_initial_preview_phase or is_full_batch_phase or is_small_batch_phase
        
        if should_generate_now:
            # Clear previous previews and data if starting a new generation cycle (initial or full batch)
            if st.session_state.generation_stage == "initial" or st.session_state.generation_stage == "full_batch_generating":
                 st.session_state.preview_html_parts = [] 
                 st.session_state.generated_image_data = {}
                 st.session_state.zip_buffer = None # Clear old zip

            preloader_and_status_container.markdown(f"""
                <div class='preloader-area'>
                    <div class='preloader'></div>
                    <span class='preloader-text'>Generating (0/{current_processing_limit})...</span>
                </div>
            """, unsafe_allow_html=True)

            # Clear buttons before generation starts for this pass
            download_buttons_container.empty() 
            generate_full_batch_button_container.empty()

            zip_buffer_current_run = io.BytesIO() # Fresh zip buffer for this generation run
            
            with zipfile.ZipFile(zip_buffer_current_run, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
                processed_count_this_run = 0
                for source_item in images_to_process_this_run:
                    file_name = source_item['name']
                    image_bytes = source_item['bytes']

                    try:
                        img_pil = Image.open(io.BytesIO(image_bytes))
                        img_pil.verify() # Check integrity
                        img_pil = Image.open(io.BytesIO(image_bytes)) # Reopen after verify

                        w, h = img_pil.size
                        if not (10 <= w <= 15000 and 10 <= h <= 15000): # Dimension check
                            st.warning(f"`{file_name}` ({w}x{h}) is outside supported dimensions (10-15000px). Skipped.")
                            processed_count_this_run += len(layouts_to_process) # Account for all its layouts
                            preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})...</span></div>", unsafe_allow_html=True)
                            continue
                        
                        if img_pil.mode not in ("RGB", "L"): img_pil = img_pil.convert("RGB")

                        palette = extract_palette(img_pil, num_colors, quantize_method_selected)
                        if not palette: st.caption(f"No palette for `{file_name}`.")

                        for pos in layouts_to_process:
                            if is_initial_preview_phase and processed_count_this_run >= current_processing_limit:
                                break # Stop if preview limit reached for this image's layouts

                            try:
                                result_img = draw_layout(
                                    img_pil.copy(), palette, pos,
                                    image_border_thickness_percent_val, 
                                    swatch_separator_thickness_percent_val,
                                    individual_swatch_border_thickness_percent_val,
                                    border_color, swatch_border_color, swatch_size_percent_val
                                )
                                
                                img_byte_arr_output = io.BytesIO()
                                base_name, _ = os.path.splitext(file_name)
                                safe_base = "".join(c if c.isalnum() or c in (' ','.','_','-') else '_' for c in base_name).rstrip()
                                output_filename = f"{safe_base}_{pos}.{extension}"

                                save_params = {}
                                if img_format == "JPEG": save_params['quality'] = 95
                                elif img_format == "WEBP":
                                    save_params['quality'] = 85
                                    if webp_lossless: save_params.update({'lossless': True, 'quality': 100})
                                
                                result_img.save(img_byte_arr_output, format=img_format, **save_params)
                                img_bytes_for_dl = img_byte_arr_output.getvalue()
                                
                                st.session_state.generated_image_data[output_filename] = img_bytes_for_dl
                                # Add to ZIP: always for full batch/small batch; also for previews if we want downloadable previews (currently not, only final zip)
                                if is_full_batch_phase or is_small_batch_phase:
                                     zipf.writestr(output_filename, img_bytes_for_dl)


                                # Create thumbnail for display
                                preview_thumb = result_img.copy()
                                preview_thumb.thumbnail((200, 200))
                                with io.BytesIO() as buf_disp:
                                    preview_thumb.save(buf_disp, format="PNG") # PNG for web display
                                    img_b64_disp = base64.b64encode(buf_disp.getvalue()).decode("utf-8")
                                
                                dl_mime = f"image/{extension}"
                                img_b64_dl = base64.b64encode(img_bytes_for_dl).decode("utf-8")
                                display_name = shorten_filename(output_filename)

                                html_item = (f"<div class='preview-item'>"
                                             f"<div class='preview-item-name' title='{output_filename}'>{display_name}</div>"
                                             f"<img src='data:image/png;base64,{img_b64_disp}' alt='{output_filename}'>"
                                             f"<a href='data:{dl_mime};base64,{img_b64_dl}' download='{output_filename}' class='download-link'>Download Image</a>"
                                             f"</div>")
                                st.session_state.preview_html_parts.append(html_item)
                                processed_count_this_run += 1

                                preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})...</span></div>", unsafe_allow_html=True)
                                if st.session_state.preview_html_parts: # Update previews progressively
                                    preview_display_area.markdown("<div id='preview-zone'>" + "\n".join(st.session_state.preview_html_parts) + "</div>", unsafe_allow_html=True)

                            except Exception as e_layout:
                                st.error(f"Layout error for {file_name} ({pos}): {e_layout}")
                                processed_count_this_run += 1 # Increment to avoid stall
                                preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})... (Error)</span></div>", unsafe_allow_html=True)
                        
                        if is_initial_preview_phase and processed_count_this_run >= current_processing_limit:
                            break # Break from images loop if preview limit reached
                    
                    except (UnidentifiedImageError, IOError) as e_pil:
                        st.warning(f"Cannot process image `{file_name}`: {e_pil}. Skipped.")
                        processed_count_this_run += len(layouts_to_process)
                        preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})... (Skipped)</span></div>", unsafe_allow_html=True)
                    except Exception as e_gen:
                        st.error(f"Unexpected error with `{file_name}`: {e_gen}. Skipped.")
                        processed_count_this_run += len(layouts_to_process)
                        preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})... (Error)</span></div>", unsafe_allow_html=True)

            preloader_and_status_container.empty() # Clear preloader after loop

            # Finalize generation stage and zip buffer
            if is_initial_preview_phase:
                 st.session_state.generation_stage = "preview_generated"
                 # No zip buffer stored yet for previews, only final batch
            elif is_full_batch_phase or is_small_batch_phase:
                 st.session_state.generation_stage = "completed"
                 zip_buffer_current_run.seek(0)
                 st.session_state.zip_buffer = zip_buffer_current_run # Store the final zip

        # --- Display Previews (always, if they exist from current or previous run) ---
        if st.session_state.preview_html_parts:
            preview_display_area.markdown(
                "<div id='preview-zone'>" + "\n".join(st.session_state.preview_html_parts) + "</div>",
                unsafe_allow_html=True
            )
        # else: # preview_display_area already has an empty div if no parts

        # --- Control Buttons based on Stage ---
        generate_full_batch_button_container.empty() # Clear first
        if st.session_state.generation_stage == "preview_generated":
            # Calculate remaining generations accurately based on total sources vs previewed sources
            num_previewed_sources = len(images_to_process_this_run) if is_initial_preview_phase and images_to_process_this_run else 0
            # This calculation for remaining might be complex if previews didn't complete for all 6
            # A simpler message:
            remaining_message = f"({total_generations - len(st.session_state.preview_html_parts)} more variations estimated)" if total_generations > len(st.session_state.preview_html_parts) else ""

            button_label = f"Large batch detected {remaining_message}. If You're satisfied with Your presets, click to generate the rest!"
            with generate_full_batch_button_container:
                 if st.button(button_label, use_container_width=True, key="generate_full_batch_button", type="secondary"): # Changed to secondary for blue
                     st.session_state.generation_stage = "full_batch_generating"
                     st.session_state.full_batch_button_clicked = True
                     # Don't clear previews here, let full batch append or replace if needed
                     # st.session_state.preview_html_parts = [] 
                     # st.session_state.generated_image_data = {}
                     st.rerun()
        
        # Download Button Logic
        download_buttons_container.empty() # Clear first
        if all_image_sources and positions: # Only show if inputs are valid
            if st.session_state.generation_stage == "completed" and st.session_state.zip_buffer and st.session_state.zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader: # Check if zip has content
                with download_buttons_container:
                    st.download_button(
                        label=f"Download All as ZIP ({extension.upper()})",
                        data=st.session_state.zip_buffer,
                        file_name=f"SwatchBatch_{output_format.lower()}.zip",
                        mime="application/zip",
                        use_container_width=True,
                        key="download_zip_active_final"
                    )
            elif st.session_state.generation_stage == "preview_generated": # Previews shown, full batch pending
                with download_buttons_container:
                    st.download_button(
                        label=f"Download All as ZIP ({extension.upper()})",
                        data=io.BytesIO(), # Dummy data
                        file_name=f"SwatchBatch_{output_format.lower()}.zip",
                        mime="application/zip",
                        use_container_width=True,
                        key="download_zip_disabled_preview_pending",
                        disabled=True,
                        help="Generate whole batch first to enable download."
                    )
            elif st.session_state.generation_stage == "initial" and st.session_state.preview_html_parts:
                 # This case implies a small batch just finished and went to 'completed', so covered by the first condition.
                 # Or, if somehow previews exist but stage is still 'initial' (should not happen with current flow)
                 with download_buttons_container:
                    st.download_button(
                        label=f"Download All as ZIP ({extension.upper()})", data=io.BytesIO(),
                        file_name="temp.zip", mime="application/zip", use_container_width=True,
                        key="download_zip_disabled_initial_with_previews", disabled=True,
                        help="Processing complete. Finalizing batch for download..." # Or similar message
                    )
            else: # Initial state, no previews generated yet, or generation ongoing
                with download_buttons_container:
                    st.download_button(
                        label=f"Download All as ZIP ({extension.upper()})", data=io.BytesIO(),
                        file_name="temp.zip", mime="application/zip", use_container_width=True,
                        key="download_zip_disabled_initial_no_previews", disabled=True,
                        help="Generate previews/batch to enable download."
                    )
        else: # No valid inputs for generation
             with download_buttons_container:
                st.download_button(
                    label=f"Download All as ZIP", data=io.BytesIO(),
                    file_name="ColorSwatches.zip", mime="application/zip", use_container_width=True,
                    key="download_zip_disabled_no_inputs_at_all", disabled=True,
                    help="Upload images and select positions to enable download."
                )


    else: # No image sources or no positions selected - initial app state
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts = []
        st.session_state.generated_image_data = {}
        st.session_state.zip_buffer = None
        st.session_state.total_generations_at_start = 0
        st.session_state.full_batch_button_clicked = False
        
        generate_full_batch_button_container.empty()
        preview_container.empty() 
        download_buttons_container.empty()
        spinner_container.empty()
        preloader_and_status_container.empty()
        
        if 'processed_sources_cache' in st.session_state: # Clear URL cache if inputs are cleared
            del st.session_state.processed_sources_cache

        if all_image_sources and not positions: # Files uploaded but no positions
            st.info("Select at least one swatch position to generate images.")
        elif not all_image_sources: # No files or URL yet
            st.info("Upload images from your device or enter an image URL to get started.")
        
        # Show a generic disabled download button
        with download_buttons_container:
            st.download_button(
                label=f"Download All as ZIP", data=io.BytesIO(),
                file_name="ColorSwatches.zip", mime="application/zip", use_container_width=True,
                key="download_zip_initial_disabled_placeholder", disabled=True,
                help="Upload images and select positions to enable download."
            )


except Exception as e:
    st.error(f"A critical error occurred: {e}")
    st.exception(e) # Logs the full traceback for debugging
    st.warning("An issue was encountered. Attempting to reset. Please refresh or try again.")

    # Attempt to reset critical session state keys
    critical_keys = ['generation_stage', 'preview_html_parts', 'generated_image_data', 
                     'zip_buffer', 'current_settings_hash', 'processed_sources_cache']
    for key in critical_keys:
        if key in st.session_state:
            del st.session_state[key]
    
    # Force re-render of uploader/input by changing keys (common Streamlit pattern for reset)
    st.session_state.file_uploader_key = f"file_uploader_{int(st.session_state.get('file_uploader_key', 'file_uploader_0').split('_')[-1]) + 1}"
    st.session_state.image_url_input_key = f"image_url_input_{int(st.session_state.get('image_url_input_key', 'image_url_input_0').split('_')[-1]) + 1}"
    
    # st.rerun() # Consider if a rerun is safe or could cause loop on persistent error

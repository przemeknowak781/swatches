import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import numpy as np
import io
import zipfile
import base64
import sys # Keep for potential future use, though not directly used now
import os
import time
import requests # For URL image fetching

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("SwatchBatch - Advanced Color Palette Generator")

# --- Initialize Session State ---
if 'generation_stage' not in st.session_state:
    st.session_state.generation_stage = "initial"
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
if 'image_url_input_key' not in st.session_state: # Key for URL input to help reset
    st.session_state.image_url_input_key = "image_url_input_0"
if 'file_uploader_key' not in st.session_state: # Key for file uploader
    st.session_state.file_uploader_key = "file_uploader_0"


# --- Global containers for dynamic content ---
spinner_container = st.empty()
preview_container = st.container()
download_buttons_container = st.container()
preloader_and_status_container = st.empty()
generate_full_batch_button_container = st.empty()
# Removed resize_message_container as explicit resizing is removed. Warnings for auto-resize can still use st.warning.


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
        if palette_full is None:
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE, kmeans=5)
            palette_full = paletted.getpalette()
            if palette_full is None: return []
        actual_palette_colors = len(palette_full) // 3
        colors_to_extract = min(num_colors, actual_palette_colors)
        extracted_palette_rgb_values = palette_full[:colors_to_extract * 3]
        return [tuple(extracted_palette_rgb_values[i:i+3]) for i in range(0, len(extracted_palette_rgb_values), 3)]
    except Exception:
        try:
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE, kmeans=5)
            palette = paletted.getpalette()
            if palette is None: return []
            return [tuple(palette[i:i+3]) for i in range(0, min(num_colors * 3, len(palette)), 3)]
        except Exception:
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
    if actual_swatch_size_px <= 0 : actual_swatch_size_px = 1

    if not colors:
        if main_border > 0:
            canvas = Image.new("RGB", (img_w + 2 * main_border, img_h + 2 * main_border), border_color)
            canvas.paste(image, (main_border, main_border))
            return canvas
        return image.copy()

    swatch_width = 0
    swatch_height = 0
    extra_width_for_last_swatch = 0
    extra_height_for_last_swatch = 0
    image_paste_x = main_border
    image_paste_y = main_border

    if position == 'top':
        canvas_h = img_h + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_w = img_w + 2 * main_border
        swatch_y = main_border
        swatch_x_start = main_border
        swatch_total_width = img_w
        if len(colors) > 0:
            swatch_width = swatch_total_width // len(colors)
            extra_width_for_last_swatch = swatch_total_width % len(colors)
        image_paste_y = main_border + actual_swatch_size_px + swatch_separator_thickness_px
    elif position == 'bottom':
        canvas_h = img_h + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_w = img_w + 2 * main_border
        swatch_y = main_border + img_h + swatch_separator_thickness_px
        swatch_x_start = main_border
        swatch_total_width = img_w
        if len(colors) > 0:
            swatch_width = swatch_total_width // len(colors)
            extra_width_for_last_swatch = swatch_total_width % len(colors)
        image_paste_y = main_border
    elif position == 'left':
        canvas_w = img_w + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_h = img_h + 2 * main_border
        swatch_x = main_border
        swatch_y_start = main_border
        swatch_total_height = img_h
        if len(colors) > 0:
            swatch_height = swatch_total_height // len(colors)
            extra_height_for_last_swatch = swatch_total_height % len(colors)
        image_paste_x = main_border + actual_swatch_size_px + swatch_separator_thickness_px
    elif position == 'right':
        canvas_w = img_w + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_h = img_h + 2 * main_border
        swatch_x = main_border + img_w + swatch_separator_thickness_px
        swatch_y_start = main_border
        swatch_total_height = img_h
        if len(colors) > 0:
            swatch_height = swatch_total_height // len(colors)
            extra_height_for_last_swatch = swatch_total_height % len(colors)
        image_paste_x = main_border
    else:
        return image.copy()

    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    canvas.paste(image, (image_paste_x, image_paste_y))
    draw = ImageDraw.Draw(canvas)

    for i, color_tuple in enumerate(colors):
        current_swatch_width = swatch_width
        current_swatch_height = swatch_height
        x0, y0, x1, y1 = 0, 0, 0, 0 # Initialize to avoid UnboundLocalError

        if position in ['top', 'bottom']:
            if i == len(colors) - 1: current_swatch_width += extra_width_for_last_swatch
            x0 = swatch_x_start + i * swatch_width
            x1 = x0 + current_swatch_width
            y0_sw = swatch_y # Renamed to avoid conflict with outer scope y0
            y1_sw = swatch_y + actual_swatch_size_px
            draw.rectangle([x0, y0_sw, x1, y1_sw], fill=tuple(color_tuple))
            if internal_swatch_border_thickness > 0 and i < len(colors) - 1:
                draw.line([(x1, y0_sw), (x1, y1_sw)], fill=swatch_border_color, width=internal_swatch_border_thickness)
        else: # 'left' or 'right'
            if i == len(colors) - 1: current_swatch_height += extra_height_for_last_swatch
            y0_sw = swatch_y_start + i * swatch_height # Renamed
            y1_sw = y0_sw + current_swatch_height
            x0_sw = swatch_x # Renamed
            x1_sw = swatch_x + actual_swatch_size_px
            draw.rectangle([x0_sw, y0_sw, x1_sw, y1_sw], fill=tuple(color_tuple))
            if internal_swatch_border_thickness > 0 and i < len(colors) - 1:
                draw.line([(x0_sw, y1_sw), (x1_sw, y1_sw)], fill=swatch_border_color, width=internal_swatch_border_thickness)

    if main_border > 0:
        draw.line([(0, 0), (canvas_w - 1, 0)], fill=border_color, width=main_border)
        draw.line([(0, canvas_h - 1), (canvas_w - 1, canvas_h - 1)], fill=border_color, width=main_border)
        draw.line([(0, 0), (0, canvas_h - 1)], fill=border_color, width=main_border)
        draw.line([(canvas_w - 1, 0), (canvas_w - 1, canvas_h - 1)], fill=border_color, width=main_border)

    if swatch_separator_thickness_px > 0:
        if position == 'top':
            line_y = main_border + actual_swatch_size_px
            draw.line([(main_border, line_y), (main_border + img_w, line_y)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'bottom':
            line_y = main_border + img_h
            draw.line([(main_border, line_y), (main_border + img_w, line_y)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'left':
            line_x = main_border + actual_swatch_size_px
            draw.line([(line_x, main_border), (line_x, main_border + img_h)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'right':
            line_x = main_border + img_w
            draw.line([(line_x, main_border), (line_x, main_border + img_h)], fill=swatch_border_color, width=swatch_separator_thickness_px)
    return canvas


# --- Input Columns ---
col1, col2, col3 = st.columns(3)

# --- Top-level exception handling ---
try:
    with col1:
        st.subheader("Upload Images")
        image_url = st.text_input("Or enter image URL", key=st.session_state.image_url_input_key, placeholder="https://example.com/image.jpg")

        allowed_extensions = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif", "ico"]
        uploaded_files_from_uploader = st.file_uploader(
            "Choose images from your device",
            accept_multiple_files=True,
            type=allowed_extensions,
            key=st.session_state.file_uploader_key
        )

        all_image_sources = [] # To store {'name': str, 'bytes': bytes, 'source_type': 'file'/'url'}

        # Process URL input
        if image_url:
            try:
                # Simple check to avoid re-fetching if URL hasn't changed and we already processed it
                # This is a basic check; more robust would involve hashing the URL or checking against already processed names
                is_new_url = True
                for src in st.session_state.get('processed_sources_cache', []):
                    if src['name'] == image_url and src['source_type'] == 'url': # Using URL as name for simplicity
                        all_image_sources.append(src)
                        is_new_url = False
                        st.info(f"Using cached image from URL: {shorten_filename(image_url)}")
                        break
                
                if is_new_url:
                    st.info(f"Fetching image from URL: {image_url}...")
                    # Add headers to mimic a browser request, can help with some sites
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                    response = requests.get(image_url, timeout=15, headers=headers, stream=True)
                    response.raise_for_status()

                    # Check content length to prevent downloading excessively large files
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > 20 * 1024 * 1024: # 20MB limit
                        st.error(f"Image from URL {image_url} is too large (>{int(content_length)/(1024*1024):.1f}MB). Max 20MB allowed. Skipped.")
                    else:
                        image_bytes = response.content # Read all content now
                        
                        url_file_name_base = os.path.basename(image_url.split("?")[0].strip())
                        if not url_file_name_base: url_file_name_base = "image_from_url"
                        
                        detected_format = is_valid_image_header(image_bytes[:12])
                        if detected_format:
                            url_file_name, _ = os.path.splitext(url_file_name_base)
                            final_url_file_name = f"{url_file_name}.{detected_format}"
                            
                            source_data = {'name': final_url_file_name, 'bytes': image_bytes, 'source_type': 'url', 'original_input': image_url}
                            all_image_sources.append(source_data)
                            
                            # Add to a temporary cache to avoid re-download on immediate rerun if URL is unchanged
                            if 'processed_sources_cache' not in st.session_state:
                                st.session_state.processed_sources_cache = []
                            # Avoid duplicates in cache by original_input
                            if not any(item['original_input'] == image_url for item in st.session_state.processed_sources_cache):
                                st.session_state.processed_sources_cache.append(source_data)

                            st.success(f"Successfully fetched and validated: {final_url_file_name}")
                        else:
                            st.warning(f"Could not determine a valid image format for URL: {image_url}. Content might not be a direct image link or is an unsupported type. Skipped.")
            except requests.exceptions.MissingSchema:
                st.error(f"Invalid URL: {image_url}. Please include http:// or https://.")
            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching image from URL {image_url}: {e}. Check the URL and your internet connection.")
            except Exception as e: # Catch other potential errors during URL processing
                st.error(f"An unexpected error occurred while processing the URL {image_url}: {e}")


        # Process uploaded files
        if uploaded_files_from_uploader:
            allowed_extensions_set = set([f".{ext.lower()}" for ext in allowed_extensions])
            for file_obj in uploaded_files_from_uploader:
                file_name = file_obj.name
                try:
                    file_obj.seek(0)
                    file_bytes_sample = file_obj.read(12)
                    file_obj.seek(0)
                    detected_format = is_valid_image_header(file_bytes_sample)

                    if detected_format is None:
                        st.warning(f"File `{file_name}` does not appear to be a valid image based on its header. Skipped.")
                        continue
                    
                    file_extension = os.path.splitext(file_name)[1].lower()
                    if file_extension not in allowed_extensions_set:
                         st.warning(f"`{file_name}` has an unusual extension (`{file_extension}`). Processing based on detected header.")

                    all_image_sources.append({'name': file_name, 'bytes': file_obj.getvalue(), 'source_type': 'file', 'original_input': file_name})
                except Exception as e:
                     st.error(f"Error processing uploaded file `{file_name}`: {e}. Skipped.")
                     continue
        
        # Clear URL input after processing to allow new URL entry without manual deletion
        # This is a bit of a hack; ideally Streamlit would offer a clear button for text_input
        if image_url and (st.session_state.generation_stage == "initial" or st.session_state.generation_stage == "completed"):
             if any(src['original_input'] == image_url and src['source_type'] == 'url' for src in all_image_sources):
                st.session_state.image_url_input_key = f"image_url_input_{int(st.session_state.image_url_input_key.split('_')[-1]) + 1}"
                # st.experimental_rerun() # Can be too aggressive, let user decide next action

        st.subheader("Output Options")
        # Removed resize options
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
        row1_layout = st.columns(2)
        row2_layout = st.columns(2)
        if row1_layout[0].toggle("Top", value=True, key="pos_top"): positions.append("top")
        if row1_layout[1].toggle("Left", value=True, key="pos_left"): positions.append("left")
        if row2_layout[0].toggle("Bottom", value=True, key="pos_bottom"): positions.append("bottom")
        if row2_layout[1].toggle("Right", key="pos_right"): positions.append("right")

        quant_method_label = st.selectbox("Palette extraction", ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"], 0, key="quant_method")
        quant_method_map = {"MEDIANCUT": Image.MEDIANCUT, "MAXCOVERAGE": Image.MAXCOVERAGE, "FASTOCTREE": Image.FASTOCTREE}
        quantize_method_selected = quant_method_map[quant_method_label]
        num_colors = st.slider("Number of swatches", 2, 12, 6, key="num_colors")
        
        # Swatch size as a percentage of shorter image dimension
        swatch_size_percent_val = st.slider("Swatch size (% of shorter image dim.)", 1.0, 50.0, 20.0, step=0.5, key="swatch_size_percent", help="Swatch thickness as a percentage of the image's shorter dimension.")

    with col3:
        st.subheader("Borders (Lines)")
        # Sliders now take percentage values relative to shorter image dimension
        image_border_thickness_percent_val = st.slider("Image Border (% of shorter dim.)", 0.0, 10.0, 0.0, step=0.1, key="image_border_thickness_percent")
        swatch_separator_thickness_percent_val = st.slider("Swatch-Image Separator (% of shorter dim.)", 0.0, 10.0, 0.0, step=0.1, key="swatch_separator_thickness_percent")
        individual_swatch_border_thickness_percent_val = st.slider("Individual Swatch Border (% of shorter dim.)", 0.0, 10.0, 0.0, step=0.1, key="individual_swatch_border_thickness_percent")
        
        border_color = st.color_picker("Main Border Color", "#FFFFFF", key="border_color")
        swatch_border_color = st.color_picker("Swatch Border Color", "#FFFFFF", key="swatch_border_color")

    # --- Check for settings change to reset state ---
    # Create a hash of current relevant settings
    # Using frozenset for lists of dicts requires dicts to be hashable (e.g., tuples of items)
    processed_sources_tuple = tuple(
        (src['name'], src['bytes'].__hash__(), src['source_type']) for src in all_image_sources # Hash bytes for uniqueness
    )

    current_settings = (
        processed_sources_tuple, # Based on combined list of image sources
        frozenset(positions),
        # Removed resize_option, scale_percent
        output_format,
        webp_lossless,
        quant_method_label,
        num_colors,
        swatch_size_percent_val,
        image_border_thickness_percent_val, # Use new percent var
        swatch_separator_thickness_percent_val, # Use new percent var
        individual_swatch_border_thickness_percent_val, # Use new percent var
        border_color,
        swatch_border_color,
        image_url # Include image_url in settings hash
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
        # Clear processed_sources_cache if settings change significantly (e.g. new files uploaded, not just URL typed)
        # This logic might need refinement based on desired caching behavior
        if 'processed_sources_cache' in st.session_state and processed_sources_tuple != st.session_state.get('previous_sources_tuple_for_cache_check', None):
             del st.session_state.processed_sources_cache


    st.session_state.current_settings_hash = current_settings_hash
    st.session_state.previous_sources_tuple_for_cache_check = processed_sources_tuple


    # --- Main Generation Logic ---
    if all_image_sources and positions:
        total_generations = len(all_image_sources) * len(positions)
        st.session_state.total_generations_at_start = total_generations

        st.markdown("---")
        preview_display_area = preview_container.empty()
        preview_display_area.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True) # Initial empty zone

        images_to_process_for_preview = []
        layouts_to_process = positions
        processing_limit_count = total_generations # Default to all

        if st.session_state.generation_stage == "initial" and total_generations > 10:
            # For preview, process up to first 6 unique image sources for all their layouts
            unique_sources_for_preview = all_image_sources[:6]
            images_to_process_for_preview = unique_sources_for_preview
            processing_limit_count = len(images_to_process_for_preview) * len(layouts_to_process)
        elif st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
            images_to_process_for_preview = all_image_sources # Process all
            # processing_limit_count is already total_generations

        
        if st.session_state.generation_stage in ["initial", "full_batch_generating"] or (total_generations <= 10 and not st.session_state.preview_html_parts): # Also generate if small batch and no previews yet
            
            # Only show preloader if we are actually about to generate (not just displaying existing previews)
            if not st.session_state.preview_html_parts or st.session_state.generation_stage == "full_batch_generating":
                preloader_and_status_container.markdown(f"""
                    <div class='preloader-area'>
                        <div class='preloader'></div>
                        <span class='preloader-text'>Generating previews (0/{processing_limit_count})...</span>
                    </div>
                """, unsafe_allow_html=True)

            download_buttons_container.empty()
            generate_full_batch_button_container.empty()

            # If it's the start of a new generation (initial or full batch), clear previous previews
            if st.session_state.generation_stage == "initial" or st.session_state.generation_stage == "full_batch_generating":
                 st.session_state.preview_html_parts = [] # Clear for new generation
                 st.session_state.generated_image_data = {} # Clear for new generation

            zip_buffer = io.BytesIO() # Initialize zip buffer for this generation pass
            
            # Use compresslevel=0 (ZIP_STORED) for speed, as images are already compressed.
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
                current_processing_count = 0
                for source_idx, image_source_item in enumerate(images_to_process_for_preview):
                    file_name = image_source_item['name']
                    image_bytes_content = image_source_item['bytes']

                    try:
                        image_stream = io.BytesIO(image_bytes_content)
                        image = Image.open(image_stream)
                        image.verify()
                        image_stream.seek(0) # Re-open after verify
                        image = Image.open(image_stream)

                        w, h = image.size
                        if not (10 <= w <= 15000 and 10 <= h <= 15000): # Increased max dim slightly
                            st.warning(f"`{file_name}` has an unsupported resolution ({w}x{h}). Max 15000px. Skipped.")
                            current_processing_count += len(layouts_to_process) 
                            # Update preloader text omitted for brevity here, but should be included
                            continue
                        
                        # Convert image to RGB if it's not, to ensure compatibility
                        if image.mode not in ("RGB", "L"): image = image.convert("RGB")

                        palette = extract_palette(image, num_colors, quantize_method=quantize_method_selected)
                        if not palette: st.caption(f"Could not extract palette for `{file_name}`. Swatches might be empty.")

                        for pos_idx, pos in enumerate(layouts_to_process):
                            if st.session_state.generation_stage == "initial" and current_processing_count >= processing_limit_count:
                                break 

                            try:
                                result_img = draw_layout(
                                    image.copy(), palette, pos,
                                    image_border_thickness_percent_val, 
                                    swatch_separator_thickness_percent_val,
                                    individual_swatch_border_thickness_percent_val,
                                    border_color, swatch_border_color, swatch_size_percent_val
                                )
                                
                                # No explicit resizing here anymore. Output is original size + borders/swatches.

                                img_byte_arr = io.BytesIO()
                                base_name, _ = os.path.splitext(file_name)
                                safe_base_name = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in base_name).rstrip()
                                name_for_file = f"{safe_base_name}_{pos}.{extension}"

                                save_params = {}
                                if img_format == "JPEG": save_params['quality'] = 95
                                elif img_format == "WEBP":
                                    save_params['quality'] = 85
                                    if webp_lossless: save_params.update({'lossless': True, 'quality': 100})
                                
                                result_img.save(img_byte_arr, format=img_format, **save_params)
                                img_bytes_for_download = img_byte_arr.getvalue()
                                
                                # Store image data for potential later use (e.g. if not zipping immediately)
                                st.session_state.generated_image_data[name_for_file] = img_bytes_for_download

                                # Add to ZIP file only during full batch generation or small batches (<=10 total)
                                # Or if it's a preview stage, but we intend to make the zip downloadable after preview too.
                                # For now, only zip if it's the final generation stage.
                                if st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
                                    zipf.writestr(name_for_file, img_bytes_for_download)

                                # Create a thumbnail for the preview
                                preview_img_for_display = result_img.copy()
                                preview_img_for_display.thumbnail((200, 200)) # Thumbnail size
                                with io.BytesIO() as buffer_display:
                                    preview_img_for_display.save(buffer_display, format="PNG") # PNG for preview consistency
                                    img_base64 = base64.b64encode(buffer_display.getvalue()).decode("utf-8")
                                
                                img_base64_download = base64.b64encode(img_bytes_for_download).decode("utf-8")
                                download_mime_type = f"image/{extension}"
                                display_name = shorten_filename(name_for_file)

                                single_item_html = f"<div class='preview-item'>"
                                single_item_html += f"<div class='preview-item-name' title='{name_for_file}'>{display_name}</div>"
                                single_item_html += f"<img src='data:image/png;base64,{img_base64}' alt='Preview of {name_for_file}'>"
                                single_item_html += f"<a href='data:{download_mime_type};base64,{img_base64_download}' download='{name_for_file}' class='download-link'>Download Image</a>"
                                single_item_html += "</div>"
                                
                                st.session_state.preview_html_parts.append(single_item_html)
                                current_processing_count += 1

                                # Update preloader text and preview display progressively
                                preloader_and_status_container.markdown(f"""
                                    <div class='preloader-area'>
                                        <div class='preloader'></div>
                                        <span class='preloader-text'>Generating previews... {current_processing_count}/{processing_limit_count}</span>
                                    </div>
                                """, unsafe_allow_html=True)
                                
                                # Progressive preview update
                                if st.session_state.preview_html_parts:
                                    preview_display_area.markdown(
                                        "<div id='preview-zone'>" + "\n".join(st.session_state.preview_html_parts) + "</div>",
                                        unsafe_allow_html=True
                                    )

                            except Exception as e_layout:
                                st.error(f"Error creating layout for {file_name} (pos: {pos}): {e_layout}")
                                current_processing_count += 1 
                                # Update preloader text
                                preloader_and_status_container.markdown(f"""
                                    <div class='preloader-area'>
                                        <div class='preloader'></div>
                                        <span class='preloader-text'>Generating previews... {current_processing_count}/{processing_limit_count} (Error)</span>
                                    </div>
                                """, unsafe_allow_html=True)
                        
                        if st.session_state.generation_stage == "initial" and current_processing_count >= processing_limit_count:
                            break # Break from outer loop (images)
                    
                    except (UnidentifiedImageError, Exception) as e_img:
                        st.warning(f"Could not process image: `{file_name}`. Error: {e}. Skipped.")
                        current_processing_count += len(layouts_to_process)
                        preloader_and_status_container.markdown(f"""
                            <div class='preloader-area'>
                                <div class='preloader'></div>
                                <span class='preloader-text'>Generating previews... {current_processing_count}/{processing_limit_count} (Skipped File)</span>
                            </div>
                        """, unsafe_allow_html=True)
                        continue
            
            # After loop, store zip buffer if it was a full generation
            if st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
                zip_buffer.seek(0)
                st.session_state.zip_buffer = zip_buffer
            
            preloader_and_status_container.empty() # Clear preloader

            # Update generation stage
            if st.session_state.generation_stage == "initial" and total_generations > 10:
                 st.session_state.generation_stage = "preview_generated"
            elif st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
                 st.session_state.generation_stage = "completed"

        # --- Display Previews and Buttons based on Stage (even if not re-generated this run) ---
        if st.session_state.preview_html_parts:
            preview_display_area.markdown(
                "<div id='preview-zone'>" + "\n".join(st.session_state.preview_html_parts) + "</div>",
                unsafe_allow_html=True
            )
        else: # Ensure preview zone is there for CSS if empty
            preview_display_area.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True)


        if st.session_state.generation_stage == "preview_generated":
            with generate_full_batch_button_container:
                 if st.button(f"Large batch detected ({total_generations - len(st.session_state.preview_html_parts)} more to generate). Click to generate the rest!", use_container_width=True, key="generate_full_batch_button", type="primary"):
                     st.session_state.generation_stage = "full_batch_generating"
                     st.session_state.full_batch_button_clicked = True
                     st.session_state.preview_html_parts = [] # Clear previews to regenerate all for full batch
                     st.session_state.generated_image_data = {}
                     st.rerun()
        else:
            generate_full_batch_button_container.empty()

        if st.session_state.generation_stage == "completed" and st.session_state.zip_buffer and st.session_state.zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader + 100 :
            with download_buttons_container:
                st.download_button(
                    label=f"Download All as ZIP ({extension.upper()})",
                    data=st.session_state.zip_buffer,
                    file_name=f"SwatchBatch_{output_format.lower()}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key="download_zip_final"
                )
        elif not (st.session_state.generation_stage == "completed" and st.session_state.zip_buffer and st.session_state.zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader + 100):
             download_buttons_container.empty()
             if all_image_sources and positions and st.session_state.generation_stage != "preview_generated": # Show disabled if inputs are there but not ready
                 with download_buttons_container:
                     st.download_button(
                         label=f"Download All as ZIP ({extension.upper()})",
                         data=io.BytesIO(),
                         file_name="temp.zip",
                         mime="application/zip",
                         use_container_width=True,
                         key="download_zip_disabled_placeholder_main",
                         disabled=True,
                         help="Generation not complete or no images to download."
                     )


    else: # No image sources or no positions selected
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts = []
        st.session_state.generated_image_data = {}
        st.session_state.zip_buffer = None
        st.session_state.total_generations_at_start = 0
        st.session_state.full_batch_button_clicked = False
        generate_full_batch_button_container.empty()
        preview_container.empty() # Clear preview area
        download_buttons_container.empty()
        spinner_container.empty()
        preloader_and_status_container.empty()
        if 'processed_sources_cache' in st.session_state: # Clear cache if inputs are cleared
            del st.session_state.processed_sources_cache


        if all_image_sources and not positions:
            st.info("Select at least one swatch position to generate images.")
        elif not all_image_sources:
            st.info("Upload images from your device or enter an image URL to get started.")
        
        # Show a disabled download button if no inputs
        with download_buttons_container:
            st.download_button(
                label=f"Download All as ZIP", # Generic label
                data=io.BytesIO(),
                file_name="ColorSwatches.zip",
                mime="application/zip",
                use_container_width=True,
                key="download_zip_initial_disabled_no_input",
                disabled=True,
                help="Upload images and select positions to enable download."
            )


except Exception as e:
    st.error(f"An critical error occurred in the application: {e}")
    st.exception(e)
    st.warning("Attempting to reset application state. Please refresh the page or try your action again. If the issue persists, the input files/URL might be problematic.")

    # Basic reset of session state keys to try and recover
    keys_to_reset = ['generation_stage', 'preview_html_parts', 'generated_image_data', 
                     'zip_buffer', 'total_generations_at_start', 'current_settings_hash', 
                     'full_batch_button_clicked', 'processed_sources_cache']
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]
    
    # Increment keys for uploader/input to force re-render if possible
    st.session_state.file_uploader_key = f"file_uploader_{int(st.session_state.get('file_uploader_key', 'file_uploader_0').split('_')[-1]) + 1}"
    st.session_state.image_url_input_key = f"image_url_input_{int(st.session_state.get('image_url_input_key', 'image_url_input_0').split('_')[-1]) + 1}"
    
    # st.experimental_rerun() # Use with caution, can lead to loops if error is persistent on rerun

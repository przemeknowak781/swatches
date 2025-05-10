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
if 'current_settings_hash_at_generation_start' not in st.session_state: # For checking changes during generation
    st.session_state.current_settings_hash_at_generation_start = None
if 'full_batch_button_clicked' not in st.session_state:
    st.session_state.full_batch_button_clicked = False
# if 'image_url_input_key' not in st.session_state: # No longer changing key for URL input
#     st.session_state.image_url_input_key = "image_url_input_0"
if 'file_uploader_key' not in st.session_state:
    st.session_state.file_uploader_key = "file_uploader_0"
if 'processed_sources_cache' not in st.session_state: # Persistent cache for URL fetched data
    st.session_state.processed_sources_cache = []
if 'show_bmc_button' not in st.session_state:
    st.session_state.show_bmc_button = False


# --- Global containers for dynamic content ---
spinner_container = st.empty()
preview_container = st.container()
download_buttons_container = st.container()
bmc_container = st.container() # For the Buy Me A Coffee button
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
    div[data-testid="stButton"] > button[type="button"].st-emotion-cache- LcTzUn.e1nzilvr2 {
        background-color: #007BFF !important; 
        color: white !important; 
        border-color: #007BFF !important; 
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
    if len(filename) > max_len:
        name, ext = os.path.splitext(filename)
        back_chars_name = max(0, back_chars - len(ext))
        return f"{name[:front_chars]}...{name[-back_chars_name:]}{ext}"
    return filename

def is_valid_image_header(file_bytes):
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
    img_w, img_h = image.size
    shorter_dimension = min(img_w, img_h)

    image_border_thickness_px = int(shorter_dimension * (image_border_percent / 100))
    swatch_separator_thickness_px = int(shorter_dimension * (swatch_separator_percent / 100))
    individual_swatch_border_thickness_px = int(shorter_dimension * (individual_swatch_border_percent / 100))

    if image_border_percent > 0 and image_border_thickness_px == 0: image_border_thickness_px = 1
    if swatch_separator_percent > 0 and swatch_separator_thickness_px == 0: swatch_separator_thickness_px = 1
    if individual_swatch_border_percent > 0 and individual_swatch_border_thickness_px == 0: individual_swatch_border_thickness_px = 1
    
    main_border = image_border_thickness_px
    internal_swatch_border_thickness = individual_swatch_border_thickness_px
    actual_swatch_size_px = int(shorter_dimension * (swatch_size_percent_of_shorter_dim / 100))
    if actual_swatch_size_px <= 0 and swatch_size_percent_of_shorter_dim > 0 : actual_swatch_size_px = 1
    elif actual_swatch_size_px <= 0: actual_swatch_size_px = 0

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
        swatch_y_coord = main_border
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
        image_paste_y = main_border
    elif position == 'left':
        canvas_w = img_w + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_h = img_h + 2 * main_border
        swatch_x_coord = main_border
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
        image_paste_x = main_border
    else: return image.copy()

    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    canvas.paste(image, (image_paste_x, image_paste_y))
    draw = ImageDraw.Draw(canvas)

    for i, color_tuple in enumerate(colors):
        current_swatch_width = swatch_width
        current_swatch_height = swatch_height
        
        if position in ['top', 'bottom']:
            if i == len(colors) - 1: current_swatch_width += extra_width_for_last_swatch
            rect_x0 = swatch_x_start + i * swatch_width
            rect_x1 = rect_x0 + current_swatch_width
            rect_y0 = swatch_y_coord
            rect_y1 = swatch_y_coord + actual_swatch_size_px
        else:
            if i == len(colors) - 1: current_swatch_height += extra_height_for_last_swatch
            rect_y0 = swatch_y_start + i * swatch_height
            rect_y1 = rect_y0 + current_swatch_height
            rect_x0 = swatch_x_coord
            rect_x1 = swatch_x_coord + actual_swatch_size_px
        
        draw.rectangle([rect_x0, rect_y0, rect_x1, rect_y1], fill=tuple(color_tuple))

        if internal_swatch_border_thickness > 0 and i < len(colors) - 1:
            if position in ['top', 'bottom']:
                draw.line([(rect_x1, rect_y0), (rect_x1, rect_y1)], fill=swatch_border_color, width=internal_swatch_border_thickness)
            else:
                draw.line([(rect_x0, rect_y1), (rect_x1, rect_y1)], fill=swatch_border_color, width=internal_swatch_border_thickness)

    if main_border > 0:
        draw.line([(0, 0), (canvas_w - 1, 0)], fill=border_color, width=main_border)
        draw.line([(0, canvas_h - 1), (canvas_w - 1, canvas_h - 1)], fill=border_color, width=main_border)
        draw.line([(0, 0), (0, canvas_h - 1)], fill=border_color, width=main_border)
        draw.line([(canvas_w - 1, 0), (canvas_w - 1, canvas_h - 1)], fill=border_color, width=main_border)

    if swatch_separator_thickness_px > 0 and actual_swatch_size_px > 0:
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

# --- Function to get current settings tuple and hash ---
def get_settings_tuple_and_hash(all_image_sources_list, positions_list, output_format_val, webp_lossless_val,
                                quant_method_label_val, num_colors_val, swatch_size_val,
                                image_border_val, swatch_sep_val, indiv_swatch_border_val,
                                border_color_val, swatch_border_color_val):
    processed_sources_tuple = tuple(
        (src['name'], src['bytes'].__hash__(), src['source_type'], src.get('original_input')) for src in all_image_sources_list
    )
    current_settings = (
        processed_sources_tuple, 
        frozenset(positions_list),
        output_format_val, webp_lossless_val,
        quant_method_label_val, num_colors_val,
        swatch_size_val,
        image_border_val, 
        swatch_sep_val, 
        indiv_swatch_border_val,
        border_color_val, swatch_border_color_val,
    )
    return current_settings, hash(current_settings)

# --- Input Columns ---
col1, col2, col3 = st.columns(3)

# --- Top-level exception handling ---
try:
    with col1:
        st.subheader("Upload Images")
        allowed_extensions = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif", "ico"]
        uploaded_files_from_uploader = st.file_uploader(
            "There's no limit of uploaded files, however I recommend batches below 200 generations to ensure app stability.",
            accept_multiple_files=True,
            type=allowed_extensions,
            key=st.session_state.file_uploader_key
        )
        image_url = st.text_input("Or enter image URL", key="image_url_input", placeholder="https://example.com/image.jpg") # Removed key change

    # --- Consolidate Image Sources (Files, Cache, New URL) ---
    all_image_sources = []
    processed_input_identifiers = set() # To track 'original_input' values and avoid duplicates

    # 1. Process uploaded files
    if uploaded_files_from_uploader:
        allowed_extensions_set = set([f".{ext.lower()}" for ext in allowed_extensions])
        for file_obj in uploaded_files_from_uploader:
            file_name = file_obj.name
            if file_name in processed_input_identifiers: continue # Already processed (e.g. if uploader allows same file twice)
            try:
                file_obj.seek(0)
                file_bytes_sample = file_obj.read(12)
                file_obj.seek(0)
                detected_format_from_header = is_valid_image_header(file_bytes_sample)

                if detected_format_from_header is None:
                    st.warning(f"File `{file_name}` does not appear to be a valid image. Skipped.")
                    continue
                
                # file_extension_original = os.path.splitext(file_name)[1].lower()
                # if file_extension_original not in allowed_extensions_set and file_extension_original:
                #      st.warning(f"`{file_name}` has unusual extension. Processing based on detected header: '{detected_format_from_header}'.")

                source_data = {'name': file_name, 
                               'bytes': file_obj.getvalue(), 
                               'source_type': 'file', 
                               'original_input': file_name}
                all_image_sources.append(source_data)
                processed_input_identifiers.add(file_name)
            except Exception as e:
                 st.error(f"Error processing uploaded file `{file_name}`: {e}. Skipped.")
                 continue

    # 2. Load from persistent URL cache (st.session_state.processed_sources_cache)
    for cached_src in st.session_state.processed_sources_cache:
        if cached_src['source_type'] == 'url' and cached_src['original_input'] not in processed_input_identifiers:
            all_image_sources.append(cached_src)
            processed_input_identifiers.add(cached_src['original_input'])
            # st.info(f"Loaded from cache: {cached_src['name']}") # Optional for debugging

    # 3. Process current image_url text input
    if image_url and image_url not in processed_input_identifiers:
        try:
            # Check if this URL is already in processed_sources_cache (even if not yet in all_image_sources this run)
            found_in_global_cache = False
            for src in st.session_state.processed_sources_cache:
                if src['original_input'] == image_url and src['source_type'] == 'url':
                    all_image_sources.append(src) # Add to current list of sources
                    processed_input_identifiers.add(image_url)
                    st.info(f"Using cached image from URL: {shorten_filename(src['name'])}")
                    found_in_global_cache = True
                    break
            
            if not found_in_global_cache:
                st.info(f"Fetching image from URL: {image_url}...")
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                response = requests.get(image_url, timeout=15, headers=headers, stream=True)
                response.raise_for_status()

                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > 20 * 1024 * 1024: # 20MB limit
                    st.error(f"Image from URL {image_url} is too large (>{int(content_length)/(1024*1024):.1f}MB). Max 20MB. Skipped.")
                else:
                    image_bytes = response.content
                    url_file_name_base = os.path.basename(image_url.split("?")[0].strip()) 
                    if not url_file_name_base or '.' not in url_file_name_base: url_file_name_base = "image_from_url"
                    detected_format = is_valid_image_header(image_bytes[:12])

                    if detected_format:
                        name_part, _ = os.path.splitext(url_file_name_base)
                        final_url_file_name = f"{name_part}.{detected_format}"
                        
                        source_data = {'name': final_url_file_name, 
                                       'bytes': image_bytes, 
                                       'source_type': 'url', 
                                       'original_input': image_url}
                        all_image_sources.append(source_data)
                        processed_input_identifiers.add(image_url)
                        
                        # Add to persistent cache if not already there by original_input
                        if not any(item['original_input'] == image_url for item in st.session_state.processed_sources_cache):
                            st.session_state.processed_sources_cache.append(source_data)
                        st.success(f"Fetched and cached: {final_url_file_name}")
                    else:
                        st.warning(f"Could not validate image from URL: {image_url}. Skipped.")
        except requests.exceptions.MissingSchema:
            st.error(f"Invalid URL: '{image_url}'. Please include http:// or https://.")
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching from URL {image_url}: {e}.")
        except Exception as e: 
            st.error(f"Error processing URL {image_url}: {e}")
    
    # --- Output Options (col1 cont.) ---
    with col1:
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
        if row1_layout[0].toggle("Top", value=False, key="pos_top"): positions.append("top") # Default False
        if row1_layout[1].toggle("Left", value=True, key="pos_left"): positions.append("left") # Default True
        if row2_layout[0].toggle("Bottom", value=True, key="pos_bottom"): positions.append("bottom") # Default True
        if row2_layout[1].toggle("Right", value=False, key="pos_right"): positions.append("right") # Default False

        quant_method_label = st.selectbox("Palette extraction", ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"], 0, key="quant_method")
        quant_method_map = {"MEDIANCUT": Image.MEDIANCUT, "MAXCOVERAGE": Image.MAXCOVERAGE, "FASTOCTREE": Image.FASTOCTREE}
        quantize_method_selected = quant_method_map[quant_method_label]
        num_colors = st.slider("Number of swatches", 2, 12, 6, key="num_colors")
        
        swatch_size_percent_val = st.slider("Swatch size (% of shorter image dim.)", 0.0, 100.0, 20.0, step=0.5, key="swatch_size_percent")

    with col3:
        st.subheader("Borders (Lines)")
        image_border_thickness_percent_val = st.slider("Image Border (% of shorter dim.)", 0.0, 20.0, 5.0, step=0.1, key="image_border_thickness_percent") # Default 5%
        swatch_separator_thickness_percent_val = st.slider("Swatch-Image Separator (% of shorter dim.)", 0.0, 20.0, 3.5, step=0.1, key="swatch_separator_thickness_percent") # Default 3.5%
        individual_swatch_border_thickness_percent_val = st.slider("Individual Swatch Border (% of shorter dim.)", 0.0, 20.0, 5.0, step=0.1, key="individual_swatch_border_thickness_percent") # Default 5%
        
        border_color = st.color_picker("Main Border Color", "#FFFFFF", key="border_color")
        swatch_border_color = st.color_picker("Swatch Border Color", "#FFFFFF", key="swatch_border_color")

    # --- Check for settings change to reset state ---
    _, current_settings_hash = get_settings_tuple_and_hash(
        all_image_sources, positions, output_format, webp_lossless,
        quant_method_label, num_colors, swatch_size_percent_val,
        image_border_thickness_percent_val, swatch_separator_thickness_percent_val,
        individual_swatch_border_thickness_percent_val, border_color, swatch_border_color
    )

    if st.session_state.current_settings_hash is not None and st.session_state.current_settings_hash != current_settings_hash:
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts = []
        st.session_state.generated_image_data = {}
        st.session_state.zip_buffer = None
        st.session_state.total_generations_at_start = 0
        st.session_state.full_batch_button_clicked = False
        st.session_state.show_bmc_button = False # Reset BMC button display
        generate_full_batch_button_container.empty()
        # st.session_state.processed_sources_cache is NOT cleared here, to persist URL images across slider changes.
        # Only a full reset or explicit clear action would remove them.
        # st.info("Settings changed, resetting generation state.") # For debugging
        st.rerun() # Rerun to apply reset cleanly

    st.session_state.current_settings_hash = current_settings_hash


    # --- Main Generation Logic ---
    if all_image_sources and positions:
        total_generations = len(all_image_sources) * len(positions)
        # This is set only once when inputs are valid and before any generation starts or restarts due to settings change
        if st.session_state.generation_stage == "initial" and not st.session_state.full_batch_button_clicked :
             st.session_state.total_generations_at_start = total_generations


        st.markdown("---")
        preview_display_area = preview_container.empty()
        preview_display_area.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True) 

        images_to_process_this_run = []
        layouts_to_process = positions
        
        is_initial_preview_phase = (st.session_state.generation_stage == "initial" and total_generations > 6) # Preview if more than 6 total generations
        is_full_batch_phase = (st.session_state.generation_stage == "full_batch_generating")
        is_small_batch_phase = (st.session_state.generation_stage == "initial" and total_generations <= 6) # Auto-process if 6 or less

        current_processing_limit = total_generations

        if is_initial_preview_phase:
            max_preview_generations = 6
            if not layouts_to_process:
                images_to_process_this_run = []
            else:
                # Determine how many images to process to stay under max_preview_generations
                num_images_for_preview = max(1, max_preview_generations // len(layouts_to_process))
                images_to_process_this_run = all_image_sources[:num_images_for_preview]
            
            current_processing_limit = min(max_preview_generations, len(images_to_process_this_run) * len(layouts_to_process))
            if not images_to_process_this_run or current_processing_limit == 0: # Handle cases where no preview can be generated
                is_initial_preview_phase = False # Skip preview if it results in 0 items
                if total_generations > 0 and st.session_state.generation_stage == "initial": # If there are items but preview calc is 0
                     pass # Will show the "Large batch detected" button directly
        elif is_full_batch_phase or is_small_batch_phase:
            images_to_process_this_run = all_image_sources
        
        should_generate_now = is_initial_preview_phase or is_full_batch_phase or is_small_batch_phase
        
        if should_generate_now:
            if st.session_state.generation_stage == "initial" or st.session_state.generation_stage == "full_batch_generating":
                 st.session_state.preview_html_parts = [] 
                 st.session_state.generated_image_data = {}
                 st.session_state.zip_buffer = None
                 st.session_state.show_bmc_button = False

            preloader_and_status_container.markdown(f"""
                <div class='preloader-area'>
                    <div class='preloader'></div>
                    <span class='preloader-text'>Generating (0/{current_processing_limit})...</span>
                </div>
            """, unsafe_allow_html=True)

            download_buttons_container.empty() 
            generate_full_batch_button_container.empty()
            bmc_container.empty()

            zip_buffer_current_run = io.BytesIO()
            
            # Store the hash of settings at the moment generation starts
            st.session_state.current_settings_hash_at_generation_start = st.session_state.current_settings_hash

            with zipfile.ZipFile(zip_buffer_current_run, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
                processed_count_this_run = 0
                generation_interrupted = False
                for source_item_idx, source_item in enumerate(images_to_process_this_run):
                    if generation_interrupted: break
                    file_name = source_item['name']
                    image_bytes = source_item['bytes']

                    try:
                        img_pil = Image.open(io.BytesIO(image_bytes))
                        img_pil.verify()
                        img_pil = Image.open(io.BytesIO(image_bytes))

                        w, h = img_pil.size
                        if not (10 <= w <= 15000 and 10 <= h <= 15000):
                            st.warning(f"`{file_name}` ({w}x{h}) is outside supported dimensions. Skipped.")
                            # Increment count for all potential layouts of this skipped image
                            processed_count_this_run += len(layouts_to_process)
                            processed_count_this_run = min(processed_count_this_run, current_processing_limit) # Cap at limit
                            preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})...</span></div>", unsafe_allow_html=True)
                            continue
                        
                        if img_pil.mode not in ("RGB", "L"): img_pil = img_pil.convert("RGB")
                        palette = extract_palette(img_pil, num_colors, quantize_method_selected)
                        if not palette: st.caption(f"No palette for `{file_name}`.")

                        for pos_idx, pos in enumerate(layouts_to_process):
                            if processed_count_this_run >= current_processing_limit and is_initial_preview_phase:
                                generation_interrupted = True # Mark to break outer loop as well for preview
                                break 
                            
                            # --- Check for slider changes before generating this specific variation ---
                            _, check_hash = get_settings_tuple_and_hash(
                                all_image_sources, positions, output_format, webp_lossless,
                                quant_method_label, num_colors, swatch_size_percent_val,
                                image_border_thickness_percent_val, swatch_separator_thickness_percent_val,
                                individual_swatch_border_thickness_percent_val, border_color, swatch_border_color
                            )
                            if check_hash != st.session_state.current_settings_hash_at_generation_start:
                                st.warning("Settings changed during generation. Restarting process...")
                                st.session_state.generation_stage = "initial" # Reset to initial to force re-evaluation
                                st.session_state.preview_html_parts = []
                                st.session_state.generated_image_data = {}
                                st.session_state.zip_buffer = None
                                st.session_state.show_bmc_button = False
                                generation_interrupted = True # Mark to break outer loop
                                time.sleep(1) # Brief pause for message visibility
                                st.rerun() # This will stop current execution and restart the script

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
                                if is_full_batch_phase or is_small_batch_phase:
                                     zipf.writestr(output_filename, img_bytes_for_dl)

                                preview_thumb = result_img.copy()
                                preview_thumb.thumbnail((200, 200))
                                with io.BytesIO() as buf_disp:
                                    preview_thumb.save(buf_disp, format="PNG")
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
                                if st.session_state.preview_html_parts:
                                    preview_display_area.markdown("<div id='preview-zone'>" + "\n".join(st.session_state.preview_html_parts) + "</div>", unsafe_allow_html=True)

                            except Exception as e_layout:
                                st.error(f"Layout error for {file_name} ({pos}): {e_layout}")
                                processed_count_this_run += 1 
                                processed_count_this_run = min(processed_count_this_run, current_processing_limit)
                                preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})... (Error)</span></div>", unsafe_allow_html=True)
                        
                        if is_initial_preview_phase and processed_count_this_run >= current_processing_limit :
                             generation_interrupted = True # Ensure outer loop breaks if limit hit
                             break 
                    
                    except (UnidentifiedImageError, IOError) as e_pil:
                        st.warning(f"Cannot process image `{file_name}`: {e_pil}. Skipped.")
                        processed_count_this_run += len(layouts_to_process)
                        processed_count_this_run = min(processed_count_this_run, current_processing_limit)
                        preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})... (Skipped)</span></div>", unsafe_allow_html=True)
                    except Exception as e_gen:
                        st.error(f"Unexpected error with `{file_name}`: {e_gen}. Skipped.")
                        processed_count_this_run += len(layouts_to_process)
                        processed_count_this_run = min(processed_count_this_run, current_processing_limit)
                        preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})... (Error)</span></div>", unsafe_allow_html=True)

            preloader_and_status_container.empty()

            if not generation_interrupted: # Only finalize stage if not interrupted by slider change
                if is_initial_preview_phase:
                    st.session_state.generation_stage = "preview_generated"
                elif is_full_batch_phase or is_small_batch_phase:
                    st.session_state.generation_stage = "completed"
                    zip_buffer_current_run.seek(0)
                    st.session_state.zip_buffer = zip_buffer_current_run
                    st.session_state.show_bmc_button = True # Ready to show BMC

        if st.session_state.preview_html_parts:
            preview_display_area.markdown(
                "<div id='preview-zone'>" + "\n".join(st.session_state.preview_html_parts) + "</div>",
                unsafe_allow_html=True
            )

        generate_full_batch_button_container.empty()
        if st.session_state.generation_stage == "preview_generated": # Preview was shown, more to generate
            remaining_generations = st.session_state.total_generations_at_start - len(st.session_state.preview_html_parts)
            remaining_message = f"({remaining_generations} more variations estimated)" if remaining_generations > 0 else ""
            button_label = f"Preview ready. Generate full batch {remaining_message}"
            with generate_full_batch_button_container:
                 if st.button(button_label, use_container_width=True, key="generate_full_batch_button", type="secondary"):
                     st.session_state.generation_stage = "full_batch_generating"
                     st.session_state.full_batch_button_clicked = True
                     st.rerun()
        elif st.session_state.generation_stage == "initial" and total_generations > 6 and not images_to_process_this_run : # Large batch, but preview was skipped (e.g. 0 items in preview calc)
            with generate_full_batch_button_container:
                if st.button(f"Large batch detected ({total_generations} variations). Click to generate all.", use_container_width=True, key="generate_full_batch_button_direct", type="secondary"):
                    st.session_state.generation_stage = "full_batch_generating"
                    st.session_state.full_batch_button_clicked = True
                    st.rerun()

        download_buttons_container.empty()
        st.session_state.show_bmc_button = False # Default to false, enable only if download is active

        if all_image_sources and positions:
            if st.session_state.generation_stage == "completed" and st.session_state.zip_buffer and st.session_state.zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader:
                with download_buttons_container:
                    st.download_button(
                        label=f"Download All as ZIP ({extension.upper()})",
                        data=st.session_state.zip_buffer,
                        file_name=f"SwatchBatch_{output_format.lower()}.zip",
                        mime="application/zip",
                        use_container_width=True,
                        key="download_zip_active_final"
                    )
                    st.session_state.show_bmc_button = True # Enable BMC button
            elif st.session_state.generation_stage == "preview_generated" or \
                 (st.session_state.generation_stage == "initial" and total_generations > 6) : # Preview shown or large batch pending
                with download_buttons_container:
                    st.download_button(
                        label=f"Download All as ZIP ({extension.upper()})", data=io.BytesIO(),
                        file_name=f"temp.zip", mime="application/zip", use_container_width=True,
                        key="download_zip_disabled_preview", disabled=True,
                        help="Generate full batch to enable download."
                    )
            else: # Covers small batches just generated (should be 'completed'), or other intermediate states
                 with download_buttons_container:
                    st.download_button(
                        label=f"Download All as ZIP ({extension.upper()})", data=io.BytesIO(),
                        file_name="temp.zip", mime="application/zip", use_container_width=True,
                        key="download_zip_disabled_inter", disabled=True,
                        help="Processing not yet complete or no downloadable batch."
                    )
        else:
             with download_buttons_container:
                st.download_button(
                    label=f"Download All as ZIP", data=io.BytesIO(),
                    file_name="ColorSwatches.zip", mime="application/zip", use_container_width=True,
                    key="download_zip_disabled_no_inputs", disabled=True,
                    help="Upload images and select positions."
                )
        
        # Display Buy Me A Coffee button if conditions met
        with bmc_container:
            if st.session_state.get('show_bmc_button', False):
                st.markdown("""
                <div style="margin-top: 25px; margin-bottom: 15px; padding: 15px; text-align: center; background-color: #f0f2f6; border-radius: 8px; border: 1px solid #e0e0e0;">
                    <p style="margin-bottom: 12px; font-size: 1em; color: #333;">This app is completely free to use. Your support is greatly appreciated and helps keep it running!</p>
                    <script type="text/javascript" src="https://cdnjs.buymeacoffee.com/1.0.0/button.prod.min.js" data-name="bmc-button" data-slug="przemeknowak" data-color="#FFDD00" data-emoji="☕" data-font="Lato" data-text="Buy me a coffee" data-outline-color="#000000" data-font-color="#000000" data-coffee-color="#ffffff" ></script>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.empty()


    else: # No image sources or no positions selected
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts = []
        st.session_state.generated_image_data = {}
        st.session_state.zip_buffer = None
        st.session_state.total_generations_at_start = 0
        st.session_state.full_batch_button_clicked = False
        st.session_state.show_bmc_button = False
        
        generate_full_batch_button_container.empty()
        preview_container.empty() 
        download_buttons_container.empty()
        bmc_container.empty()
        spinner_container.empty()
        preloader_and_status_container.empty()
        
        # Consider if processed_sources_cache should be cleared here.
        # For now, let it persist unless a specific "clear all" action is added.
        # if not all_image_sources and 'processed_sources_cache' in st.session_state and st.session_state.processed_sources_cache:
        #     # If user cleared all inputs, maybe offer to clear cache or clear it automatically.
        #     # For now, keep it simple: cache persists.
        #     pass


        if all_image_sources and not positions:
            st.info("Select at least one swatch position to generate images.")
        elif not all_image_sources:
            st.info("Upload images from your device or enter an image URL to get started.")
        
        with download_buttons_container: # Show disabled download button
            st.download_button(
                label=f"Download All as ZIP", data=io.BytesIO(),
                file_name="ColorSwatches.zip", mime="application/zip", use_container_width=True,
                key="download_zip_initial_disabled_placeholder", disabled=True,
                help="Upload images and select positions to enable download."
            )


except Exception as e:
    st.error(f"A critical error occurred: {e}")
    st.exception(e)
    st.warning("An issue was encountered. Attempting to reset some states. Please refresh or try again.")

    critical_keys_on_error = ['generation_stage', 'preview_html_parts', 'generated_image_data', 
                              'zip_buffer', 'current_settings_hash', 'current_settings_hash_at_generation_start',
                              'show_bmc_button'] # Don't clear processed_sources_cache on general error
    for key in critical_keys_on_error:
        if key in st.session_state:
            try: del st.session_state[key]
            except: pass # Should not fail
    
    st.session_state.file_uploader_key = f"file_uploader_{int(st.session_state.get('file_uploader_key', 'file_uploader_0').split('_')[-1]) + 1}"
    # Don't change image_url_input_key anymore
    # st.session_state.image_url_input_key = f"image_url_input_{int(st.session_state.get('image_url_input_key', 'image_url_input_0').split('_')[-1]) + 1}"
    
    # st.rerun() # Be cautious with autorerun on exception, might cause loop.

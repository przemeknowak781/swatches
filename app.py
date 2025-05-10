import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import numpy as np
import io
import zipfile
import base64
import sys 
import os
import time
import requests 

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("SwatchBatch - Advanced Color Palette Generator")

# --- Initialize Session State (Robustly) ---
default_session_state = {
    'generation_stage': "initial", # "initial", "preview_generated", "full_batch_generating", "completed"
    'preview_html_parts': [],
    'generated_image_data': {},
    'zip_buffer': None,
    'total_generations_at_start': 0,
    'current_settings_hash': None,
    'current_settings_hash_at_generation_start': None, # For checking changes during generation
    'full_batch_button_clicked': False,
    'file_uploader_key': "file_uploader_0",
    'processed_sources_cache': [], # Persistent cache for URL fetched data
    'show_bmc_button': False,
    'image_url_current_input': "" # To manage URL input field state
}

for key, value in default_session_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

# --- Global containers for dynamic content ---
spinner_container = st.empty()
preview_container = st.container()
download_buttons_container = st.container()
bmc_container = st.container() 
preloader_and_status_container = st.empty()
generate_full_batch_button_container = st.empty()


# --- CSS for responsive columns and general styling ---
st.markdown("""
    <style>
    /* General layout and responsiveness */
    body { font-family: 'Inter', sans-serif; }
    @media (min-width: 768px) {
        .responsive-columns { display: flex; gap: 2rem; }
        .responsive-columns > div { flex: 1; }
    }
    h1, h2, h3, h4, h5, h6 { font-weight: 600; }
    .stButton>button { border-radius: 0.5rem; transition: all 0.2s ease-in-out; }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
    .stSlider > div > div > div[role="slider"] { background-color: #007bff; } /* Slider color */

    /* Preview Zone Styling */
    #preview-zone {
        display: flex; flex-wrap: nowrap; overflow-x: auto; 
        gap: 20px; padding: 20px; border-radius: 12px; /* Softer radius */
        min-height: 280px; /* Slightly taller */
        align-items: flex-start; margin-bottom: 20px; 
        background: #f8f9fa; /* Lighter background */
        border: 1px solid #dee2e6; 
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.05); /* Inner shadow for depth */
    }
    .preview-item {
        flex: 0 0 auto; display: flex; flex-direction: column; 
        align-items: center; text-align: center;
        width: 230px; /* Slightly wider */
        box-shadow: 0 6px 18px rgba(0,0,0,0.1); /* Softer, more spread shadow */
        padding: 15px; border-radius: 10px;
        background: #ffffff; border: 1px solid #e9ecef;
        transition: transform 0.2s ease-out; /* Hover effect */
    }
    .preview-item:hover { transform: translateY(-3px); }
    .preview-item img {
        width: 100%; height: auto; border-radius: 6px; 
        margin-bottom: 10px; object-fit: contain; max-height: 190px; 
    }
    .preview-item-name {
        font-size: 0.8rem; margin-bottom: 6px; color: #495057; /* Darker gray */
        word-break: break-all; height: 36px; overflow: hidden; /* Allow for two lines */
        width: 100%; text-overflow: ellipsis; white-space: normal; /* Allow wrap then ellipsis */
        line-height: 1.3;
    }
    .download-link {
        font-size: 0.75rem; color: #007bff; text-decoration: none; 
        margin-top: 8px; padding: 5px 10px; border-radius: 5px;
        background-color: #e7f3ff; border: 1px solid #cfe2ff;
        transition: background-color 0.2s ease;
    }
    .download-link:hover { background-color: #d0eaff; color: #0056b3; }

    /* Preloader Styling */
    .preloader-area {
        display: flex; align-items: center; justify-content: center; 
        margin: 25px auto; min-height: 45px; 
    }
    .preloader {
        border: 4px solid #e9ecef; border-top: 4px solid #007bff; 
        border-radius: 50%; width: 35px; height: 35px;
        animation: spin 0.8s linear infinite; margin-right: 18px; 
    }
    .preloader-text { font-size: 1.05em; color: #555e68; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

    /* Custom style for the blue "Large batch detected..." button */
    div[data-testid="stButton"] > button[kind="secondary"],
    div[data-testid="stButton"] > button.st-emotion-cache- LcTzUn.e1nzilvr2 { /* Example class, might change */
        background-color: #007BFF !important; color: white !important; 
        border-color: #007BFF !important;
    }
    div[data-testid="stButton"] > button[kind="secondary"]:hover,
    div[data-testid="stButton"] > button.st-emotion-cache- LcTzUn.e1nzilvr2:hover {
        background-color: #0056b3 !important; border-color: #0056b3 !important;
    }
    .stDownloadButton button { width: 100%; background-color: #28a745; border-color: #28a745; }
    .stDownloadButton button:hover { background-color: #218838; border-color: #1e7e34; }

    /* BMC Button Container */
    .bmc-button-container {
        margin-top: 25px; margin-bottom: 15px; padding: 20px; 
        text-align: center; background-color: #f0f2f6; 
        border-radius: 8px; border: 1px solid #e0e0e0;
    }
    .bmc-button-container p {
        margin-bottom: 15px; font-size: 1em; color: #333;
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
    actual_swatch_size_px = int(shorter_dimension * (swatch_size_percent_of_shorter_dim / 100))
    if actual_swatch_size_px <= 0 and swatch_size_percent_of_shorter_dim > 0 : actual_swatch_size_px = 1
    elif actual_swatch_size_px <= 0: actual_swatch_size_px = 0

    if not colors:
        if main_border > 0:
            canvas = Image.new("RGB", (img_w + 2 * main_border, img_h + 2 * main_border), border_color)
            canvas.paste(image, (main_border, main_border))
            return canvas
        return image.copy()

    swatch_width = 0; swatch_height = 0
    extra_width_for_last_swatch = 0; extra_height_for_last_swatch = 0
    image_paste_x = main_border; image_paste_y = main_border

    common_canvas_args = {"width_add": 0, "height_add": 0, "swatch_x_or_y_coord": main_border, "paste_offset_dim": 0}

    if position in ['top', 'bottom']:
        common_canvas_args["height_add"] = actual_swatch_size_px + swatch_separator_thickness_px
        swatch_total_dim = img_w
        if len(colors) > 0: swatch_width = swatch_total_dim // len(colors)
        extra_width_for_last_swatch = swatch_total_dim % len(colors) if len(colors) > 0 else 0
        if position == 'top':
            common_canvas_args["paste_offset_dim"] = actual_swatch_size_px + swatch_separator_thickness_px
            image_paste_y = main_border + common_canvas_args["paste_offset_dim"]
        else: # bottom
            common_canvas_args["swatch_x_or_y_coord"] = main_border + img_h + swatch_separator_thickness_px
    elif position in ['left', 'right']:
        common_canvas_args["width_add"] = actual_swatch_size_px + swatch_separator_thickness_px
        swatch_total_dim = img_h
        if len(colors) > 0: swatch_height = swatch_total_dim // len(colors)
        extra_height_for_last_swatch = swatch_total_dim % len(colors) if len(colors) > 0 else 0
        if position == 'left':
            common_canvas_args["paste_offset_dim"] = actual_swatch_size_px + swatch_separator_thickness_px
            image_paste_x = main_border + common_canvas_args["paste_offset_dim"]
        else: # right
            common_canvas_args["swatch_x_or_y_coord"] = main_border + img_w + swatch_separator_thickness_px
    else: return image.copy()

    canvas_w = img_w + 2 * main_border + common_canvas_args["width_add"]
    canvas_h = img_h + 2 * main_border + common_canvas_args["height_add"]
    
    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    canvas.paste(image, (image_paste_x, image_paste_y))
    draw = ImageDraw.Draw(canvas)

    swatch_x_current = common_canvas_args["swatch_x_or_y_coord"] if position in ['left', 'right'] else main_border
    swatch_y_current = common_canvas_args["swatch_x_or_y_coord"] if position in ['top', 'bottom'] else main_border

    for i, color_tuple in enumerate(colors):
        current_sw_w = swatch_width + (extra_width_for_last_swatch if i == len(colors) -1 else 0)
        current_sw_h = swatch_height + (extra_height_for_last_swatch if i == len(colors) -1 else 0)

        if position in ['top', 'bottom']:
            rect = [swatch_x_current, swatch_y_current, swatch_x_current + current_sw_w, swatch_y_current + actual_swatch_size_px]
            draw.rectangle(rect, fill=tuple(color_tuple))
            if individual_swatch_border_thickness_px > 0 and i < len(colors) - 1:
                draw.line([(rect[2], rect[1]), (rect[2], rect[3])], fill=swatch_border_color, width=individual_swatch_border_thickness_px)
            swatch_x_current += current_sw_w
        else: # left or right
            rect = [swatch_x_current, swatch_y_current, swatch_x_current + actual_swatch_size_px, swatch_y_current + current_sw_h]
            draw.rectangle(rect, fill=tuple(color_tuple))
            if individual_swatch_border_thickness_px > 0 and i < len(colors) - 1:
                draw.line([(rect[0], rect[3]), (rect[2], rect[3])], fill=swatch_border_color, width=individual_swatch_border_thickness_px)
            swatch_y_current += current_sw_h
            
    if main_border > 0:
        draw.rectangle([0,0, canvas_w-1, canvas_h-1], outline=border_color, width=main_border)

    if swatch_separator_thickness_px > 0 and actual_swatch_size_px > 0:
        if position == 'top':
            line_y = main_border + actual_swatch_size_px
            draw.line([(main_border, line_y), (canvas_w - main_border -1, line_y)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'bottom':
            line_y = main_border + img_h 
            draw.line([(main_border, line_y), (canvas_w - main_border-1, line_y)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'left':
            line_x = main_border + actual_swatch_size_px
            draw.line([(line_x, main_border), (line_x, canvas_h - main_border -1)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'right':
            line_x = main_border + img_w
            draw.line([(line_x, main_border), (line_x, canvas_h - main_border-1)], fill=swatch_border_color, width=swatch_separator_thickness_px)
    return canvas


# --- Function to get current settings tuple and hash ---
def get_settings_tuple_and_hash(all_image_sources_list, positions_list, output_format_val, webp_lossless_val,
                                quant_method_label_val, num_colors_val, swatch_size_val,
                                image_border_val, swatch_sep_val, indiv_swatch_border_val,
                                border_color_val, swatch_border_color_val):
    # Hash bytes content directly for more robust change detection if bytes objects are reused
    processed_sources_tuple = tuple(
        (src['name'], hash(src['bytes']), src['source_type'], src.get('original_input')) for src in all_image_sources_list
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

try:
    with col1:
        st.subheader("🖼️ Upload Images")
        allowed_extensions = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif", "ico"]
        uploaded_files_from_uploader = st.file_uploader(
            "Upload multiple files. For stability, batches under 200 generations are recommended.",
            accept_multiple_files=True,
            type=allowed_extensions,
            key=st.session_state.file_uploader_key
        )
        # Use st.session_state to manage text_input value if we want to clear it
        if 'image_url_current_input' not in st.session_state: st.session_state.image_url_current_input = ""
        
        image_url_input_val = st.text_input(
            "Or enter image URL", 
            value=st.session_state.image_url_current_input, 
            key="image_url_field", # Stable key
            placeholder="https://example.com/image.jpg"
        )
        # Update session state if input changes (for potential clearing later)
        if image_url_input_val != st.session_state.image_url_current_input:
            st.session_state.image_url_current_input = image_url_input_val
            st.rerun() # Rerun to process the new URL immediately

    all_image_sources = []
    processed_input_identifiers = set() 

    if uploaded_files_from_uploader:
        for file_obj in uploaded_files_from_uploader:
            file_name = file_obj.name
            if file_name in processed_input_identifiers: continue
            try:
                file_obj.seek(0); file_bytes_sample = file_obj.read(12); file_obj.seek(0)
                if is_valid_image_header(file_bytes_sample) is None:
                    st.warning(f"File `{file_name}` is not a valid image. Skipped."); continue
                source_data = {'name': file_name, 'bytes': file_obj.getvalue(), 'source_type': 'file', 'original_input': file_name}
                all_image_sources.append(source_data)
                processed_input_identifiers.add(file_name)
            except Exception as e: st.error(f"Error processing `{file_name}`: {e}. Skipped.")

    for cached_src in st.session_state.processed_sources_cache:
        if cached_src['source_type'] == 'url' and cached_src['original_input'] not in processed_input_identifiers:
            all_image_sources.append(cached_src)
            processed_input_identifiers.add(cached_src['original_input'])

    current_url_to_process = st.session_state.image_url_current_input # Use the state variable
    if current_url_to_process and current_url_to_process not in processed_input_identifiers:
        try:
            # No need to check global cache again here, if it's not in processed_input_identifiers, it's new or not yet added this session
            st.info(f"Fetching from URL: {current_url_to_process}...")
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(current_url_to_process, timeout=15, headers=headers, stream=True)
            response.raise_for_status()
            if int(response.headers.get('Content-Length', 0)) > 20 * 1024 * 1024:
                st.error(f"Image from URL is too large (>20MB). Skipped."); raise Exception("File too large")

            image_bytes = response.content
            url_file_name_base = os.path.basename(current_url_to_process.split("?")[0].strip()) or "image_from_url"
            detected_format = is_valid_image_header(image_bytes[:12])
            if detected_format:
                final_url_file_name = f"{os.path.splitext(url_file_name_base)[0]}.{detected_format}"
                source_data = {'name': final_url_file_name, 'bytes': image_bytes, 'source_type': 'url', 'original_input': current_url_to_process}
                all_image_sources.append(source_data)
                processed_input_identifiers.add(current_url_to_process)
                if not any(item['original_input'] == current_url_to_process for item in st.session_state.processed_sources_cache):
                    st.session_state.processed_sources_cache.append(source_data)
                st.success(f"Fetched: {final_url_file_name}")
                st.session_state.image_url_current_input = "" # Clear input field in state
                st.rerun() # Rerun to reflect cleared field and process image
            else: st.warning(f"Could not validate image from URL. Skipped.")
        except requests.exceptions.MissingSchema: st.error(f"Invalid URL. Include http:// or https://.")
        except requests.exceptions.RequestException as e: st.error(f"Error fetching URL: {e}.")
        except Exception as e: 
            if "File too large" not in str(e): # Avoid double message for large files
                st.error(f"Error processing URL: {e}")
            # Do not clear URL here, user might want to correct it
    
    with col1:
        st.subheader("⚙️ Output Options")
        output_format = st.selectbox("Output format", ["JPG", "PNG", "WEBP"], key="output_format")
        webp_lossless = st.checkbox("Lossless WEBP", value=False, key="webp_lossless") if output_format == "WEBP" else False
        format_map = {"JPG": ("JPEG", "jpg"), "PNG": ("PNG", "png"), "WEBP": ("WEBP", "webp")}
        img_format, extension = format_map[output_format]

    with col2:
        st.subheader("🎨 Layout Settings")
        positions = []
        st.write("Swatch position(s):")
        col2_row1, col2_row2 = st.columns(2), st.columns(2)
        if col2_row1[0].toggle("Top", value=False, key="pos_top"): positions.append("top")
        if col2_row1[1].toggle("Left", value=True, key="pos_left"): positions.append("left")
        if col2_row2[0].toggle("Bottom", value=True, key="pos_bottom"): positions.append("bottom")
        if col2_row2[1].toggle("Right", value=False, key="pos_right"): positions.append("right")

        quant_method_label = st.selectbox("Palette extraction", ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"], 0, key="quant_method")
        quant_method_map = {"MEDIANCUT": Image.MEDIANCUT, "MAXCOVERAGE": Image.MAXCOVERAGE, "FASTOCTREE": Image.FASTOCTREE}
        quantize_method_selected = quant_method_map[quant_method_label]
        num_colors = st.slider("Number of swatches", 2, 12, 6, key="num_colors")
        swatch_size_percent_val = st.slider("Swatch size (% of shorter image dim.)", 0.0, 100.0, 20.0, step=0.5, key="swatch_size_percent")

    with col3:
        st.subheader("📏 Borders & Lines")
        image_border_thickness_percent_val = st.slider("Image Border (%)", 0.0, 20.0, 5.0, step=0.1, key="image_border_thickness_percent")
        swatch_separator_thickness_percent_val = st.slider("Swatch-Image Separator (%)", 0.0, 20.0, 3.5, step=0.1, key="swatch_separator_thickness_percent")
        individual_swatch_border_thickness_percent_val = st.slider("Individual Swatch Border (%)", 0.0, 20.0, 5.0, step=0.1, key="individual_swatch_border_thickness_percent")
        border_color = st.color_picker("Main Border Color", "#FFFFFF", key="border_color")
        swatch_border_color = st.color_picker("Swatch Border Color", "#FFFFFF", key="swatch_border_color")

    _, new_settings_hash = get_settings_tuple_and_hash(
        all_image_sources, positions, output_format, webp_lossless,
        quant_method_label, num_colors, swatch_size_percent_val,
        image_border_thickness_percent_val, swatch_separator_thickness_percent_val,
        individual_swatch_border_thickness_percent_val, border_color, swatch_border_color
    )

    if st.session_state.current_settings_hash is not None and st.session_state.current_settings_hash != new_settings_hash:
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts = []
        st.session_state.generated_image_data = {}
        st.session_state.zip_buffer = None
        st.session_state.total_generations_at_start = 0
        st.session_state.full_batch_button_clicked = False
        st.session_state.show_bmc_button = False
        generate_full_batch_button_container.empty()
        # st.info("Settings changed, resetting generation state.") # For debugging
        st.session_state.current_settings_hash = new_settings_hash # Update before rerun
        st.rerun() 

    st.session_state.current_settings_hash = new_settings_hash


    if all_image_sources and positions:
        total_generations = len(all_image_sources) * len(positions)
        if st.session_state.generation_stage == "initial" and not st.session_state.full_batch_button_clicked :
             st.session_state.total_generations_at_start = total_generations

        st.markdown("---")
        preview_display_area = preview_container.empty()
        preview_display_area.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True) 

        images_to_process_this_run = []
        
        is_initial_preview_phase = (st.session_state.generation_stage == "initial" and total_generations > 6)
        is_full_batch_phase = (st.session_state.generation_stage == "full_batch_generating")
        is_small_batch_phase = (st.session_state.generation_stage == "initial" and total_generations <= 6)

        current_processing_limit = total_generations

        if is_initial_preview_phase:
            max_preview_generations = 6
            num_images_for_preview = max(1, max_preview_generations // len(positions)) if positions else 0
            images_to_process_this_run = all_image_sources[:num_images_for_preview]
            current_processing_limit = min(max_preview_generations, len(images_to_process_this_run) * len(positions))
            if not images_to_process_this_run or current_processing_limit == 0: is_initial_preview_phase = False
        elif is_full_batch_phase or is_small_batch_phase:
            images_to_process_this_run = all_image_sources
        
        should_generate_now = is_initial_preview_phase or is_full_batch_phase or is_small_batch_phase
        
        if should_generate_now:
            if st.session_state.generation_stage == "initial" or st.session_state.generation_stage == "full_batch_generating": # Reset for new batch
                 st.session_state.preview_html_parts = [] 
                 st.session_state.generated_image_data = {}
                 st.session_state.zip_buffer = None
                 st.session_state.show_bmc_button = False

            preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating (0/{current_processing_limit})...</span></div>", unsafe_allow_html=True)
            download_buttons_container.empty(); generate_full_batch_button_container.empty(); bmc_container.empty()
            zip_buffer_current_run = io.BytesIO()
            
            st.session_state.current_settings_hash_at_generation_start = st.session_state.current_settings_hash

            with zipfile.ZipFile(zip_buffer_current_run, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
                processed_count_this_run = 0
                generation_interrupted = False
                for source_item in images_to_process_this_run:
                    if generation_interrupted: break
                    file_name = source_item['name']; image_bytes = source_item['bytes']
                    try:
                        img_pil = Image.open(io.BytesIO(image_bytes)); img_pil.verify()
                        img_pil = Image.open(io.BytesIO(image_bytes)) # Reopen
                        w, h = img_pil.size
                        if not (10 <= w <= 15000 and 10 <= h <= 15000):
                            st.warning(f"`{file_name}` ({w}x{h}) outside dimensions. Skipped.")
                            processed_count_this_run += len(positions)
                            processed_count_this_run = min(processed_count_this_run, current_processing_limit)
                            preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})...</span></div>", unsafe_allow_html=True)
                            continue
                        if img_pil.mode not in ("RGB", "L"): img_pil = img_pil.convert("RGB")
                        palette = extract_palette(img_pil, num_colors, quantize_method_selected)

                        for pos in positions:
                            if processed_count_this_run >= current_processing_limit and is_initial_preview_phase:
                                generation_interrupted = True; break 
                            
                            if st.session_state.current_settings_hash != st.session_state.current_settings_hash_at_generation_start:
                                st.warning("Settings changed during generation. Restarting...")
                                st.session_state.generation_stage = "initial" 
                                st.session_state.preview_html_parts = []; st.session_state.generated_image_data = {}
                                st.session_state.zip_buffer = None; st.session_state.show_bmc_button = False
                                generation_interrupted = True; time.sleep(0.5); st.rerun()

                            try:
                                result_img = draw_layout(img_pil.copy(), palette, pos, image_border_thickness_percent_val, 
                                                         swatch_separator_thickness_percent_val, individual_swatch_border_thickness_percent_val,
                                                         border_color, swatch_border_color, swatch_size_percent_val)
                                img_byte_arr_output = io.BytesIO()
                                safe_base = "".join(c if c.isalnum() or c in (' ','.','_','-') else '_' for c in os.path.splitext(file_name)[0]).rstrip()
                                output_filename = f"{safe_base}_{pos}.{extension}"
                                save_params = {'quality': 95} if img_format == "JPEG" else ({'quality': 85, 'lossless': webp_lossless} if img_format == "WEBP" else {})
                                if img_format == "WEBP" and webp_lossless: save_params['quality'] = 100

                                result_img.save(img_byte_arr_output, format=img_format, **save_params)
                                img_bytes_for_dl = img_byte_arr_output.getvalue()
                                st.session_state.generated_image_data[output_filename] = img_bytes_for_dl
                                if is_full_batch_phase or is_small_batch_phase: zipf.writestr(output_filename, img_bytes_for_dl)

                                preview_thumb = result_img.copy(); preview_thumb.thumbnail((200, 200))
                                with io.BytesIO() as buf_disp:
                                    preview_thumb.save(buf_disp, format="PNG")
                                    img_b64_disp = base64.b64encode(buf_disp.getvalue()).decode("utf-8")
                                
                                dl_mime = f"image/{extension}"; img_b64_dl = base64.b64encode(img_bytes_for_dl).decode("utf-8")
                                html_item = (f"<div class='preview-item'><div class='preview-item-name' title='{output_filename}'>{shorten_filename(output_filename)}</div>"
                                             f"<img src='data:image/png;base64,{img_b64_disp}' alt='{output_filename}'>"
                                             f"<a href='data:{dl_mime};base64,{img_b64_dl}' download='{output_filename}' class='download-link'>Download Image</a></div>")
                                st.session_state.preview_html_parts.append(html_item)
                                processed_count_this_run += 1
                                preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})...</span></div>", unsafe_allow_html=True)
                                if st.session_state.preview_html_parts: preview_display_area.markdown("<div id='preview-zone'>" + "\n".join(st.session_state.preview_html_parts) + "</div>", unsafe_allow_html=True)
                            except Exception as e_layout:
                                st.error(f"Layout error for {file_name} ({pos}): {e_layout}")
                                processed_count_this_run = min(processed_count_this_run + 1, current_processing_limit)
                                preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})... (Error)</span></div>", unsafe_allow_html=True)
                        if generation_interrupted : break 
                    except (UnidentifiedImageError, IOError) as e_pil:
                        st.warning(f"Cannot process `{file_name}`: {e_pil}. Skipped.")
                        processed_count_this_run = min(processed_count_this_run + len(positions), current_processing_limit)
                        preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})... (Skipped)</span></div>", unsafe_allow_html=True)
                    except Exception as e_gen:
                        st.error(f"Error with `{file_name}`: {e_gen}. Skipped.")
                        processed_count_this_run = min(processed_count_this_run + len(positions), current_processing_limit)
                        preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating ({processed_count_this_run}/{current_processing_limit})... (Error)</span></div>", unsafe_allow_html=True)

            preloader_and_status_container.empty()
            if not generation_interrupted:
                if is_initial_preview_phase: st.session_state.generation_stage = "preview_generated"
                elif is_full_batch_phase or is_small_batch_phase:
                    st.session_state.generation_stage = "completed"
                    zip_buffer_current_run.seek(0)
                    st.session_state.zip_buffer = zip_buffer_current_run
                    st.session_state.show_bmc_button = True 

        if st.session_state.preview_html_parts:
            preview_display_area.markdown("<div id='preview-zone'>" + "\n".join(st.session_state.preview_html_parts) + "</div>", unsafe_allow_html=True)

        generate_full_batch_button_container.empty()
        if st.session_state.generation_stage == "preview_generated":
            remaining = st.session_state.total_generations_at_start - len(st.session_state.preview_html_parts)
            btn_label = f"Preview ready. Generate full batch ({remaining} more)" if remaining > 0 else "Generate full batch"
            if generate_full_batch_button_container.button(btn_label, use_container_width=True, key="gen_full_batch_btn", type="secondary"):
                st.session_state.generation_stage = "full_batch_generating"; st.session_state.full_batch_button_clicked = True; st.rerun()
        elif st.session_state.generation_stage == "initial" and total_generations > 6 and not images_to_process_this_run : 
            if generate_full_batch_button_container.button(f"Large batch ({total_generations} variations). Click to generate.", use_container_width=True, key="gen_full_direct_btn", type="secondary"):
                st.session_state.generation_stage = "full_batch_generating"; st.session_state.full_batch_button_clicked = True; st.rerun()

        download_buttons_container.empty()
        # st.session_state.show_bmc_button = False # Reset before check
        if st.session_state.generation_stage == "completed" and st.session_state.zip_buffer and st.session_state.zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader:
            download_buttons_container.download_button(label=f"Download All as ZIP ({extension.upper()})", data=st.session_state.zip_buffer,
                                 file_name=f"SwatchBatch_{output_format.lower()}.zip", mime="application/zip", use_container_width=True, key="dl_zip_final")
            # st.session_state.show_bmc_button = True # Already set when generation completed
        elif st.session_state.generation_stage == "preview_generated" or (st.session_state.generation_stage == "initial" and total_generations > 6) :
            download_buttons_container.download_button(label=f"Download All as ZIP ({extension.upper()})", data=io.BytesIO(), disabled=True,
                                 file_name="temp.zip", mime="application/zip", use_container_width=True, key="dl_zip_disabled_preview", help="Generate full batch for download.")
        else: # Initial, or small batch just finished (covered by 'completed')
            download_buttons_container.download_button(label=f"Download All as ZIP ({extension.upper()})", data=io.BytesIO(), disabled=True,
                                 file_name="temp.zip", mime="application/zip", use_container_width=True, key="dl_zip_disabled_inter", help="Processing or no batch ready.")
        
        with bmc_container:
            if st.session_state.get('show_bmc_button', False):
                st.markdown("""
                <div class="bmc-button-container">
                    <p>This app is free! Your support is greatly appreciated and helps keep it running.</p>
                    <script type="text/javascript" src="https://cdnjs.buymeacoffee.com/1.0.0/button.prod.min.js" data-name="bmc-button" data-slug="przemeknowak" data-color="#FFDD00" data-emoji="☕" data-font="Lato" data-text="Buy me a coffee" data-outline-color="#000000" data-font-color="#000000" data-coffee-color="#ffffff" ></script>
                </div>
                """, unsafe_allow_html=True)
            else: st.empty()
    else: # No image sources or no positions selected
        # Reset states if inputs become invalid
        st.session_state.generation_stage = "initial"; st.session_state.preview_html_parts = []
        st.session_state.generated_image_data = {}; st.session_state.zip_buffer = None
        st.session_state.total_generations_at_start = 0; st.session_state.full_batch_button_clicked = False
        st.session_state.show_bmc_button = False
        
        generate_full_batch_button_container.empty(); preview_container.empty(); download_buttons_container.empty()
        bmc_container.empty(); spinner_container.empty(); preloader_and_status_container.empty()
        
        if all_image_sources and not positions: st.info("🎯 Select at least one swatch position.")
        elif not all_image_sources: st.info("⬆️ Upload images or enter a URL to start.")
        
        download_buttons_container.download_button(label=f"Download All as ZIP", data=io.BytesIO(), disabled=True,
                             file_name="ColorSwatches.zip", mime="application/zip", use_container_width=True, 
                             key="dl_zip_initial_disabled", help="Upload images and select positions.")

except Exception as e:
    st.error(f"🚨 A critical error occurred: {e}")
    st.exception(e)
    st.warning("An issue was encountered. Some states might be reset. Please refresh or try again.")
    # Minimal reset on critical error to avoid losing all user work like cache
    st.session_state.generation_stage = "initial"
    st.session_state.current_settings_hash_at_generation_start = None # Important to reset this
    # Avoid clearing 'processed_sources_cache' or 'current_settings_hash' here to preserve user inputs/settings
    # st.rerun() # Avoid auto-rerun in critical error handler to prevent loops

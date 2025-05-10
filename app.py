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
import gc # Import garbage collector

# --- Constants ---
MAX_PROCESSING_DIMENSION = 1920  # Max width/height for processing to reduce memory
                                # Adjust as needed based on server capacity and desired quality
MAX_PREVIEWS_IN_ZONE = 10 # Max previews to generate/show to avoid browser slowdown

# --- Global Variables ---
total_processed_for_preview = 0 # Counter for preview generation, needs to be global

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("Free Color Palette Generator from Image")
st.markdown("Instantly Generate Color Palettes from Multiple Images: Your Free, Open-Source Tool for Pinterest Automation, Instagram Content, and Batch Design Work.")


# --- Initialize Session State (Robustly) ---
default_session_state = {
    'generation_stage': "initial", # "initial", "preview_generated", "full_batch_generating", "completed"
    'preview_html_parts': [],
    'generated_image_data': {},
    'zip_buffer': None,
    'total_generations_at_start': 0,
    'current_settings_hash': None,
    'current_settings_hash_at_generation_start': None,
    'full_batch_button_clicked': False,
    'file_uploader_key': "file_uploader_0",
    'processed_sources_cache': [],
    'image_url_current_input': "",
    'download_completed_message': False
}

for key, value in default_session_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

# --- Global containers for dynamic content ---
spinner_container = st.empty()
preview_container = st.container()
download_buttons_container = st.container()
post_download_message_container = st.container()
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
        gap: 20px; padding: 20px; border-radius: 12px; 
        min-height: 280px; 
        align-items: flex-start; margin-bottom: 20px; 
        background: #f8f9fa; /* Parent container background */
        border: 1px solid #dee2e6; 
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.05); 
    }
    .preview-item {
        flex: 0 0 auto; display: flex; flex-direction: column; 
        align-items: center; text-align: center;
        width: 230px; 
        box-shadow: 0 6px 18px rgba(0,0,0,0.1); 
        padding: 15px; border-radius: 10px;
        background: #f0f0f0; /* Individual preview item background - light gray */
        border: 1px solid #e0e0e0; /* Slightly darker border for items */
        transition: transform 0.2s ease-out; 
    }
    .preview-item:hover { transform: translateY(-3px); }
    .preview-item img {
        width: 100%; height: auto; border-radius: 6px; 
        margin-bottom: 10px; object-fit: contain; max-height: 190px; 
    }
    .preview-item-name {
        font-size: 0.8rem; margin-bottom: 6px; color: #495057; 
        word-break: break-all; height: 36px; overflow: hidden; 
        width: 100%; text-overflow: ellipsis; white-space: normal; 
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
    div[data-testid="stButton"] > button.st-emotion-cache- LcTzUn.e1nzilvr2 { 
        background-color: #007BFF !important; color: white !important; 
        border-color: #007BFF !important;
    }
    div[data-testid="stButton"] > button[kind="secondary"]:hover,
    div[data-testid="stButton"] > button.st-emotion-cache- LcTzUn.e1nzilvr2:hover {
        background-color: #0056b3 !important; border-color: #0056b3 !important;
    }
    /* Download ZIP Button Styling */
    .stDownloadButton button { 
        width: 100%; 
        background-color: #28a745 !important; /* Green background */
        border-color: #28a745 !important;
        color: white !important; /* White text */
        font-weight: bold !important; /* Bold text */
        text-shadow: none !important; /* Remove any text shadow/highlight */
    }
    .stDownloadButton button:hover { 
        background-color: #218838 !important; 
        border-color: #1e7e34 !important; 
        color: white !important;
    }
    .stDownloadButton button:disabled {
        background-color: #f6f6f6 !important; /* Gray when disabled */
        border-color: #6c757d !important;
        color: #ced4da !important;
    }


    /* Post-Download Message & Button Styling */
    .post-download-message-container {
        margin-top: 25px; margin-bottom: 15px; padding: 20px; 
        text-align: center; background-color: #e7f3ff; /* Light blue background */
        border-radius: 8px; border: 1px solid #cfe2ff; /* Blue border */
    }
    .post-download-message-container p {
        margin-bottom: 15px; font-size: 1em; color: #004085; /* Darker blue text */
    }
    .buy-dev-coffee-button {
        background-color: #fff7dc !important; /* Standard BMC yellow */
        color: #000000 !important; /* Black text */
        border: 1px solid #ffeba9 !important;
        padding: 10px 20px !important;
        text-decoration: none !important;
        font-weight: bold !important;
        border-radius: 0.5rem !important;
        display: inline-block !important;
        transition: background-color 0.2s ease, transform 0.2s ease !important;
    }
    .buy-dev-coffee-button:hover {
        background-color: #ffeba9 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1) !important;
    }

    /* SEO Text Section Styling */
    .seo-section { margin-top: 40px; padding-top: 20px; border-top: 1px solid #dee2e6; }
    .seo-section h2 { font-size: 1.8em; color: #343a40; margin-bottom: 0.8em;}
    .seo-section h3 { font-size: 1.4em; color: #495057; margin-top: 1.5em; margin-bottom: 0.6em;}
    .seo-section p, .seo-section li { font-size: 1em; line-height: 1.7; color: #555e68; }
    .seo-section ul { list-style-position: outside; padding-left: 20px; }
    .seo-columns { display: flex; flex-direction: row; gap: 30px; }
    .seo-column { flex: 1; }
    @media (max-width: 768px) { .seo-columns { flex-direction: column; } }
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

def resize_image_if_needed(image: Image.Image, max_dim: int) -> Image.Image:
    """Resizes an image if its width or height exceeds max_dim, preserving aspect ratio."""
    width, height = image.size
    if width > max_dim or height > max_dim:
        if width > height:
            new_width = max_dim
            new_height = int(height * (max_dim / width))
        else:
            new_height = max_dim
            new_width = int(width * (max_dim / height))
        
        try:
            resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return resized_image
        except Exception as e: # Fallback if LANCZOS fails (e.g. on some image modes)
            return image.resize((new_width, new_height)) 
    return image


# --- Color Extraction ---
def extract_palette(image, num_colors=6, quantize_method=Image.MEDIANCUT):
    img = image.convert("RGB") # Ensure image is in RGB for quantization
    try:
        # Removed kmeans parameter as it's not standard for MEDIANCUT/FASTOCTREE in Pillow
        paletted = img.quantize(colors=num_colors, method=quantize_method)
        palette_full = paletted.getpalette()

        if palette_full is None: # Fallback if first quantization fails
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE) 
            palette_full = paletted.getpalette()
            if palette_full is None: return [] # Return empty if still no palette

        actual_palette_colors = len(palette_full) // 3
        colors_to_extract = min(num_colors, actual_palette_colors)
        extracted_palette_rgb_values = palette_full[:colors_to_extract * 3]
        return [tuple(extracted_palette_rgb_values[i:i+3]) for i in range(0, len(extracted_palette_rgb_values), 3)]
    except Exception as e: # Broad exception to catch various Pillow errors during quantization
        try: # Simpler fallback without kmeans, ensuring it's not the cause of an error
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE)
            palette = paletted.getpalette()
            if palette is None: return []
            return [tuple(palette[i:i+3]) for i in range(0, min(num_colors * 3, len(palette)), 3)]
        except Exception as final_e:
            st.error(f"All palette extraction attempts failed for an image: {final_e}")
            return []

# --- Draw Layout Function ---
def draw_layout(image, colors, position,
                image_border_percent, swatch_separator_percent, individual_swatch_border_percent,
                border_color, swatch_border_color, swatch_size_percent_of_shorter_dim):
    # Ensure image is mutable and in a suitable mode (e.g., RGB)
    img_to_draw = image.copy() # Work on a copy to avoid modifying the original (resized) image

    # Handle animated images (use first frame) or images not in RGB/RGBA
    if hasattr(img_to_draw, 'is_animated') and img_to_draw.is_animated:
        try:
            img_to_draw.seek(0) # Go to the first frame
            img_to_draw = img_to_draw.convert("RGB") # Convert first frame to RGB
        except EOFError: # If it's a single frame animated image or other issue
             img_to_draw = img_to_draw.convert("RGB")
    elif img_to_draw.mode not in ("RGB", "RGBA"): # Ensure it's RGB or RGBA
        # If it's Palette mode (P), convert to RGBA to preserve potential transparency, otherwise RGB.
        convert_mode = "RGBA" if img_to_draw.mode == "P" else "RGB"
        img_to_draw = img_to_draw.convert(convert_mode)


    img_w, img_h = img_to_draw.size
    shorter_dimension = min(img_w, img_h)

    # Calculate pixel thicknesses for borders and separators
    image_border_thickness_px = int(shorter_dimension * (image_border_percent / 100))
    swatch_separator_thickness_px = int(shorter_dimension * (swatch_separator_percent / 100))
    individual_swatch_border_thickness_px = int(shorter_dimension * (individual_swatch_border_percent / 100))

    # Ensure minimum 1px thickness if percentage > 0 but calculated px is 0
    if image_border_percent > 0 and image_border_thickness_px == 0: image_border_thickness_px = 1
    if swatch_separator_percent > 0 and swatch_separator_thickness_px == 0: swatch_separator_thickness_px = 1
    if individual_swatch_border_percent > 0 and individual_swatch_border_thickness_px == 0: individual_swatch_border_thickness_px = 1
    
    main_border = image_border_thickness_px
    actual_swatch_size_px = int(shorter_dimension * (swatch_size_percent_of_shorter_dim / 100))
    # Ensure swatch size is at least 1px if percentage > 0, or 0 if percentage is 0
    if actual_swatch_size_px <= 0 and swatch_size_percent_of_shorter_dim > 0 : actual_swatch_size_px = 1
    elif actual_swatch_size_px <= 0: actual_swatch_size_px = 0 # Explicitly 0 if percentage is 0

    # If no colors are extracted, just draw the border around the image if specified
    if not colors: 
        if main_border > 0:
            # Create a new canvas with border color, then paste the image
            canvas = Image.new("RGB", (img_w + 2 * main_border, img_h + 2 * main_border), border_color)
            # Paste the image (ensure it's RGB, especially if original was RGBA with transparency for a border-only image)
            canvas.paste(img_to_draw.convert("RGB"), (main_border, main_border)) 
            return canvas
        return img_to_draw.convert("RGB") # Return a copy, converted to RGB for consistency

    # Initialize dimensions for swatches and offsets
    swatch_width = 0; swatch_height = 0
    extra_width_for_last_swatch = 0; extra_height_for_last_swatch = 0
    image_paste_x = main_border; image_paste_y = main_border

    # Common arguments for canvas creation based on palette position
    common_canvas_args = {"width_add": 0, "height_add": 0, "swatch_x_or_y_coord": main_border, "paste_offset_dim": 0}

    if position in ['top', 'bottom']:
        common_canvas_args["height_add"] = actual_swatch_size_px + swatch_separator_thickness_px
        swatch_total_dim = img_w # Swatches span the width of the image
        if len(colors) > 0: swatch_width = swatch_total_dim // len(colors)
        extra_width_for_last_swatch = swatch_total_dim % len(colors) if len(colors) > 0 else 0
        if position == 'top':
            common_canvas_args["paste_offset_dim"] = actual_swatch_size_px + swatch_separator_thickness_px
            image_paste_y = main_border + common_canvas_args["paste_offset_dim"]
        else: # bottom
            common_canvas_args["swatch_x_or_y_coord"] = main_border + img_h + swatch_separator_thickness_px
    elif position in ['left', 'right']:
        common_canvas_args["width_add"] = actual_swatch_size_px + swatch_separator_thickness_px
        swatch_total_dim = img_h # Swatches span the height of the image
        if len(colors) > 0: swatch_height = swatch_total_dim // len(colors)
        extra_height_for_last_swatch = swatch_total_dim % len(colors) if len(colors) > 0 else 0
        if position == 'left':
            common_canvas_args["paste_offset_dim"] = actual_swatch_size_px + swatch_separator_thickness_px
            image_paste_x = main_border + common_canvas_args["paste_offset_dim"]
        else: # right
            common_canvas_args["swatch_x_or_y_coord"] = main_border + img_w + swatch_separator_thickness_px
    else: # Should not happen if UI is correct
        return img_to_draw.convert("RGB")

    # Calculate final canvas dimensions
    canvas_w = img_w + 2 * main_border + common_canvas_args["width_add"]
    canvas_h = img_h + 2 * main_border + common_canvas_args["height_add"]
    
    # Create the main canvas, ensuring it's RGB for broad compatibility
    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    # Paste the original (potentially mode-converted) image onto the canvas
    # If img_to_draw has alpha (RGBA), convert to RGB before pasting on an RGB canvas to avoid errors
    # or handle alpha blending explicitly if needed (here, simple paste is fine as canvas is pre-filled)
    paste_image = img_to_draw if img_to_draw.mode == "RGB" else img_to_draw.convert("RGB")
    canvas.paste(paste_image, (image_paste_x, image_paste_y))
    draw = ImageDraw.Draw(canvas)

    # Determine starting coordinates for drawing swatches
    swatch_x_current = common_canvas_args["swatch_x_or_y_coord"] if position in ['left', 'right'] else main_border
    swatch_y_current = common_canvas_args["swatch_x_or_y_coord"] if position in ['top', 'bottom'] else main_border

    # Draw each color swatch
    for i, color_tuple in enumerate(colors):
        current_sw_w = swatch_width + (extra_width_for_last_swatch if i == len(colors) -1 else 0)
        current_sw_h = swatch_height + (extra_height_for_last_swatch if i == len(colors) -1 else 0)

        try: # Ensure color_tuple is valid
            fill_color = tuple(map(int, color_tuple))
        except (ValueError, TypeError):
            fill_color = (0,0,0) # Default to black if color is invalid

        if position in ['top', 'bottom']:
            rect = [swatch_x_current, swatch_y_current, swatch_x_current + current_sw_w, swatch_y_current + actual_swatch_size_px]
            draw.rectangle(rect, fill=fill_color)
            # Draw border between swatches if specified
            if individual_swatch_border_thickness_px > 0 and i < len(colors) - 1: 
                draw.line([(rect[2], rect[1]), (rect[2], rect[3])], fill=swatch_border_color, width=individual_swatch_border_thickness_px)
            swatch_x_current += current_sw_w
        else: # left or right
            rect = [swatch_x_current, swatch_y_current, swatch_x_current + actual_swatch_size_px, swatch_y_current + current_sw_h]
            draw.rectangle(rect, fill=fill_color)
            # Draw border between swatches if specified
            if individual_swatch_border_thickness_px > 0 and i < len(colors) - 1: 
                draw.line([(rect[0], rect[3]), (rect[2], rect[3])], fill=swatch_border_color, width=individual_swatch_border_thickness_px)
            swatch_y_current += current_sw_h
            
    # Draw main border around the entire canvas if specified
    if main_border > 0:
        outline_rect = [0,0, canvas_w-1, canvas_h-1]
        # Draw the border multiple times for thickness > 1, as Pillow's width for rectangle outline might be limited
        for i_border in range(main_border): # Use different loop variable
             draw.rectangle([outline_rect[0]+i_border, outline_rect[1]+i_border, outline_rect[2]-i_border, outline_rect[3]-i_border], outline=border_color)

    # Draw swatch separator line if specified and swatches are visible
    if swatch_separator_thickness_px > 0 and actual_swatch_size_px > 0 and len(colors) > 0 :
        if position == 'top':
            line_y = main_border + actual_swatch_size_px 
            draw.line([(main_border, line_y), (canvas_w - main_border -1, line_y)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'bottom':
            line_y = main_border + img_h # Separator is between image and swatches
            draw.line([(main_border, line_y), (canvas_w - main_border-1, line_y)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'left':
            line_x = main_border + actual_swatch_size_px
            draw.line([(line_x, main_border), (line_x, canvas_h - main_border -1)], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'right':
            line_x = main_border + img_w # Separator is between image and swatches
            draw.line([(line_x, main_border), (line_x, canvas_h - main_border-1)], fill=swatch_border_color, width=swatch_separator_thickness_px)
    return canvas

# --- Function to get current settings tuple and hash ---
def get_settings_tuple_and_hash(all_image_sources_list, positions_list, output_format_val, webp_lossless_val, quant_method_label_val, num_colors_val, swatch_size_val, image_border_val, swatch_sep_val, indiv_swatch_border_val, border_color_val, swatch_border_color_val):
    # Create a hashable representation of image sources (name, bytes hash, type, original input)
    processed_sources_tuple = tuple( (src['name'], hash(src['bytes']), src['source_type'], src.get('original_input')) for src in all_image_sources_list )
    # Combine all settings into a tuple for hashing
    current_settings = (
        processed_sources_tuple,
        frozenset(positions_list), # Use frozenset for hashability of list contents
        output_format_val, webp_lossless_val, quant_method_label_val, num_colors_val,
        swatch_size_val, image_border_val, swatch_sep_val, indiv_swatch_border_val,
        border_color_val, swatch_border_color_val,
    )
    return current_settings, hash(current_settings)

# --- Callback for download button ---
def handle_download_click():
    st.session_state.download_completed_message = True


# --- Input Columns ---
col1, col2, col3 = st.columns(3)

try: # Main try-except block for the entire app UI and logic
    # --- Image Sources ---
    all_image_sources = [] # This will hold dicts: {'name': str, 'bytes': BytesIO, 'source_type': str, 'original_input': str}

    with col1:
        st.subheader("Upload Images")
        allowed_extensions = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif", "ico"]
        # Use the file_uploader_key from session state to allow resetting
        uploaded_files_from_uploader = st.file_uploader(
            "Upload multiple files. For stability, batches under 200 generations are recommended.",
            accept_multiple_files=True,
            type=allowed_extensions,
            key=st.session_state.file_uploader_key
        )
        if uploaded_files_from_uploader:
            for uploaded_file in uploaded_files_from_uploader:
                all_image_sources.append({
                    'name': uploaded_file.name,
                    'bytes': uploaded_file.getvalue(), # Read file bytes
                    'source_type': 'upload',
                    'original_input': uploaded_file.name
                })

    with col2:
        st.subheader("Or Fetch from URL(s)")
        image_urls_input = st.text_area("Enter image URLs (one per line)", value=st.session_state.image_url_current_input, height=150)
        st.session_state.image_url_current_input = image_urls_input # Persist input

        if st.button("Fetch Images from URLs", key="fetch_urls_button"):
            urls = [url.strip() for url in image_urls_input.splitlines() if url.strip()]
            if urls:
                url_fetch_progress = st.progress(0)
                url_status_messages = st.empty()
                fetched_count = 0
                error_messages = []
                for i, url in enumerate(urls):
                    try:
                        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 SwatchBatchBot/1.0'}
                        response = requests.get(url, timeout=10, stream=True, headers=headers)
                        response.raise_for_status() # Check for HTTP errors
                        
                        # Validate content type more reliably
                        content_type = response.headers.get('Content-Type', '').lower()
                        if not any(img_ext in content_type for img_ext in ['jpeg', 'jpg', 'png', 'webp', 'gif', 'bmp', 'tiff', 'ico']):
                            # If content-type is not specific, try to infer from URL extension
                            file_ext_from_url = os.path.splitext(url.split('?')[0])[-1].lower().replace('.', '')
                            if file_ext_from_url not in allowed_extensions and not is_valid_image_header(response.content[:12]): # Check header if extension is not obvious
                                error_messages.append(f"Skipped URL (unclear image type or not an image): {shorten_filename(url, 50)}")
                                continue # Skip if not a recognized image type

                        img_bytes = response.content # Read content
                        
                        # Validate image header again after download just to be sure
                        if not is_valid_image_header(img_bytes[:12]):
                             error_messages.append(f"Skipped URL (content is not a valid image): {shorten_filename(url,50)}")
                             continue

                        filename = os.path.basename(url.split("?")[0]) # Basic filename from URL
                        if not os.path.splitext(filename)[1]: # If no extension in filename
                            detected_ext = is_valid_image_header(img_bytes[:12])
                            filename = f"{filename}.{detected_ext}" if detected_ext else f"{filename}.img"

                        all_image_sources.append({
                            'name': filename,
                            'bytes': img_bytes,
                            'source_type': 'url',
                            'original_input': url
                        })
                        fetched_count += 1
                    except requests.exceptions.RequestException as e:
                        error_messages.append(f"Error fetching {shorten_filename(url,50)}: {e}")
                    except Exception as e: # Catch other potential errors during URL processing
                        error_messages.append(f"Unexpected error with {shorten_filename(url,50)}: {e}")
                    finally:
                        url_fetch_progress.progress((i + 1) / len(urls))
                
                if error_messages:
                    url_status_messages.warning("Some URLs could not be processed:\n\n" + "\n".join(error_messages))
                elif fetched_count > 0 :
                     url_status_messages.success(f"Successfully fetched {fetched_count} image(s).")
                else: # No errors, but also no images fetched (e.g., all URLs were invalid but didn't cause exceptions)
                    url_status_messages.info("No images fetched. Check URLs or try again.")
            else: # No URLs entered
                st.info("Please enter some URLs to fetch.")


    # --- Settings in the third column ---
    with col3:
        st.subheader("Generation Settings")
        
        available_positions = ['top', 'bottom', 'left', 'right']
        selected_positions = st.multiselect(
            "Palette Position(s) (generates one image per selected position)",
            options=available_positions,
            default=['bottom']
        )

        output_format = st.selectbox("Output Format", ["PNG", "JPEG", "WEBP"], index=0)
        webp_lossless = False
        if output_format == "WEBP":
            webp_lossless = st.checkbox("WEBP Lossless", value=True)

        quantize_methods_map = {
            "Quality (Median Cut)": Image.MEDIANCUT,
            "Speed (Fast Octree)": Image.FASTOCTREE,
        }
        quantize_method_label = st.selectbox("Color Extraction Method", list(quantize_methods_map.keys()), index=0)
        quantize_method = quantize_methods_map[quantize_method_label]

        num_colors = st.slider("Number of Colors in Palette", 2, 12, 6)
        swatch_size_percent = st.slider("Swatch Size (% of shorter image dimension)", 0, 50, 15, help="Size of the color swatches relative to the shorter side of the image. Set to 0 to hide swatches (colors will still be extracted if positions are selected).")
        
        st.markdown("---") # Visual separator
        
        image_border_percent_raw = st.slider("Image Border Thickness (% of shorter image dimension)", 0, 10, 1, help="Set to 0 for no border around the original image part.")
        swatch_separator_percent_raw = st.slider("Swatch Separator Thickness (% of shorter image dimension)", 0, 5, 1, help="Thickness of the line between image and color swatches. Set to 0 for no separator.")
        individual_swatch_border_percent_raw = st.slider("Individual Swatch Border/Separator (% of shorter image dimension)", 0, 5, 0, help="Thickness of borders between individual color swatches. Set to 0 for no borders between swatches.")

        default_border_color = "#CCCCCC" # Light gray
        default_swatch_border_color = "#FFFFFF" # White

        col3_1, col3_2 = st.columns(2)
        with col3_1:
            border_color_hex = st.color_picker("Border Color (Image & Canvas)", default_border_color)
        with col3_2:
            swatch_border_color_hex = st.color_picker("Swatch Separator/Border Color", default_swatch_border_color)


    # --- Calculate current settings hash ---
    current_settings_values, current_settings_hash_val = get_settings_tuple_and_hash(
        all_image_sources, selected_positions, output_format, webp_lossless,
        quantize_method_label, num_colors, swatch_size_percent,
        image_border_percent_raw, swatch_separator_percent_raw, individual_swatch_border_percent_raw,
        border_color_hex, swatch_border_color_hex
    )
    st.session_state.current_settings_hash = current_settings_hash_val


    # --- Processing Logic ---
    total_possible_generations = len(all_image_sources) * len(selected_positions)

    def img_to_base64(pil_image, fmt='PNG', max_preview_dim=None):
        """Converts PIL image to base64 string, optionally resizing for preview."""
        buffered = io.BytesIO()
        img_to_save = pil_image # Start with the passed image
        if max_preview_dim: 
            # Important: operate on a copy if resizing, to not alter the original pil_image object
            # if it's used elsewhere (e.g. for full batch generation later)
            img_to_save = resize_image_if_needed(pil_image.copy(), max_preview_dim) 

        save_params = {}
        fmt_upper = fmt.upper() # Normalize format string
        if fmt_upper == 'JPEG':
            save_params['quality'] = 90 # Good quality for JPEG
        elif fmt_upper == 'WEBP':
            save_params['lossless'] = getattr(st.session_state, 'current_webp_lossless', True) # Use session state or default
            save_params['quality'] = 85 # Good quality for lossy WEBP
        
        # Ensure image is in a mode compatible with the target format
        if fmt_upper == 'JPEG' and img_to_save.mode == 'RGBA':
            img_to_save = img_to_save.convert('RGB') # JPEGs don't support alpha
        elif fmt_upper == 'PNG' and img_to_save.mode == 'P': # Palette mode
             img_to_save = img_to_save.convert('RGBA') # Convert to RGBA for better PNG save (preserves transparency)
        # General fallback for other modes if not L, RGB, or RGBA (WEBP handles more modes natively)
        elif img_to_save.mode not in ['RGB', 'RGBA', 'L'] and fmt_upper != 'WEBP': 
            img_to_save = img_to_save.convert('RGB')

        img_to_save.save(buffered, format=fmt_upper, **save_params)
        return base64.b64encode(buffered.getvalue()).decode()

    def process_single_image(pil_image, position_val, num_colors_val, quant_method_val,
                             image_border_val, swatch_sep_val, indiv_swatch_border_val,
                             border_color_val, swatch_border_color_val, swatch_size_val):
        """Processes a single PIL image for one position."""
        # Colors are extracted from the (potentially resized) input image
        # pil_image here is expected to be the already resized (by MAX_PROCESSING_DIMENSION) image
        colors = extract_palette(pil_image, num_colors_val, quant_method_val)
        
        # Layout is drawn using the same image and extracted colors
        generated_img = draw_layout(
            pil_image, colors, position_val,
            image_border_val, swatch_sep_val, indiv_swatch_border_val,
            border_color_val, swatch_border_color_val, swatch_size_val
        )
        return generated_img, colors


    def update_preview_zone(preview_limit=MAX_PREVIEWS_IN_ZONE): # Use constant
        """Updates the preview zone with generated images."""
        if not st.session_state.preview_html_parts:
            preview_container.empty() # Clear if no previews
            return

        num_previews_to_show = min(len(st.session_state.preview_html_parts), preview_limit)
        html_to_display = "".join(st.session_state.preview_html_parts[:num_previews_to_show])
        
        full_html = f"<div id='preview-zone'>{html_to_display}</div>"
        if len(st.session_state.preview_html_parts) > preview_limit:
            full_html += f"<p style='text-align:center; font-size:0.9em; color:#555;'>Showing {preview_limit} of {len(st.session_state.preview_html_parts)} previews. Generate full batch for all.</p>"
        
        preview_container.markdown(full_html, unsafe_allow_html=True)


    def process_image_source_and_generate(source_data, selected_pos_list, settings, is_preview_generation=False):
        """
        Processes a single image source (uploaded file or URL data)
        and generates images for selected positions.
        Updates session state for previews or full batch data.
        """
        global total_processed_for_preview # Use global keyword to modify the global counter

        try:
            # Open the original image from bytes
            original_pil_image = Image.open(io.BytesIO(source_data['bytes']))
            # Create a working copy and resize it if needed for processing (this is the main performance optimization)
            processed_pil_image = resize_image_if_needed(original_pil_image.copy(), MAX_PROCESSING_DIMENSION)
            
            # Ensure the processed image is in a common mode like RGB or RGBA
            if processed_pil_image.mode not in ('RGB', 'RGBA'):
                # Convert P mode (palette) to RGBA to preserve potential transparency, otherwise RGB
                convert_mode = 'RGBA' if processed_pil_image.mode == 'P' else 'RGB'
                processed_pil_image = processed_pil_image.convert(convert_mode)

        except UnidentifiedImageError:
            st.warning(f"Could not identify image: {shorten_filename(source_data['name'])}. Skipping.")
            return # Skip this source
        except Exception as e: # Catch other errors during image opening/initial processing
            st.error(f"Error opening or initially processing {shorten_filename(source_data['name'])}: {e}. Skipping.")
            return # Skip this source

        # Loop through each selected palette position for the current image source
        for position in selected_pos_list:
            if is_preview_generation and total_processed_for_preview >= MAX_PREVIEWS_IN_ZONE:
                # If generating previews and limit is reached, stop for this source.
                # Clean up PIL image objects for the current source before returning.
                del processed_pil_image
                del original_pil_image
                gc.collect()
                return 

            try:
                # Generate the image with palette for the current position
                # processed_pil_image is already the appropriately sized image for processing
                generated_pil_image, extracted_colors = process_single_image(
                    processed_pil_image, position, settings['num_colors'], settings['quant_method'],
                    settings['image_border'], settings['swatch_sep'], settings['indiv_swatch_border'],
                    settings['border_color'], settings['swatch_border_color'], settings['swatch_size']
                )

                # Determine the output filename
                output_fname_base = os.path.splitext(source_data['name'])[0]
                final_filename = f"{output_fname_base}_palette_{position}.{settings['output_format'].lower()}"

                if is_preview_generation:
                    # For previews, generate base64 for HTML display, potentially with further resizing for the preview display itself
                    b64_img = img_to_base64(generated_pil_image, settings['output_format'].upper(), max_preview_dim=200) 
                    hex_colors_str = ", ".join([f"#{''.join(f'{c:02x}' for c in col)}" for col in extracted_colors])
                    
                    preview_html = f"""
                    <div class='preview-item'>
                        <img src='data:image/{settings['output_format'].lower()};base64,{b64_img}' alt='{shorten_filename(final_filename)}'>
                        <p class='preview-item-name' title='{final_filename}'>{shorten_filename(final_filename, 22, 8, 8)}</p>
                        <div style='font-size:0.7em; margin-bottom:5px;'>Colors: {hex_colors_str[:50]}{'...' if len(hex_colors_str)>50 else ''}</div>
                    </div>
                    """
                    st.session_state.preview_html_parts.append(preview_html)
                    total_processed_for_preview += 1 # Increment global counter
                else: # For full batch generation
                    img_byte_arr = io.BytesIO()
                    save_params = {}
                    fmt_upper = settings['output_format'].upper()
                    if fmt_upper == 'JPEG': save_params['quality'] = 95
                    if fmt_upper == 'WEBP':
                        save_params['lossless'] = settings['webp_lossless']
                        save_params['quality'] = 90 # Adjusted for consistency
                    
                    # Ensure image is in a compatible mode for saving
                    save_image = generated_pil_image # This is the image from draw_layout
                    if fmt_upper == 'JPEG' and save_image.mode == 'RGBA':
                        save_image = save_image.convert('RGB')
                    elif save_image.mode == 'P' and fmt_upper == 'PNG': # Palette mode PNGs
                        save_image = save_image.convert('RGBA') 
                    elif save_image.mode not in ['RGB', 'RGBA', 'L'] and fmt_upper != 'WEBP': # General fallback
                         save_image = save_image.convert('RGB')

                    save_image.save(img_byte_arr, format=fmt_upper, **save_params)
                    st.session_state.generated_image_data[final_filename] = img_byte_arr.getvalue()

            except Exception as e:
                st.error(f"Error processing {shorten_filename(source_data['name'])} for position {position}: {e}")
            finally:
                # Clean up the generated image for this specific position to free memory
                if 'generated_pil_image' in locals(): del generated_pil_image
                # save_image is often an alias or converted version of generated_pil_image,
                # deleting generated_pil_image should cover it. If save_image was a distinct copy,
                # it would also need `del save_image` if it's large and no longer needed.
        
        # Clean up PIL image objects for the current source file after all its positions are processed
        del processed_pil_image
        del original_pil_image 
        gc.collect() # Collect garbage after processing each source file


    # --- UI Elements for Generating ---
    # total_processed_for_preview is a global variable, initialized at the top of the script.

    if all_image_sources and selected_positions:
        # Condition to (re)generate previews:
        # 1. Initial stage, OR
        # 2. Settings have changed since last preview/batch generation, OR
        # 3. No preview HTML parts exist (e.g., after a "Start Over")
        if st.session_state.generation_stage == "initial" or \
           st.session_state.current_settings_hash != st.session_state.get('current_settings_hash_at_generation_start', None) or \
           not st.session_state.preview_html_parts: 

            if st.button("🚀 Generate Initial Previews (up to 10)", type="primary", key="generate_preview_button"):
                # ** CRITICAL SECTION FOR THE SyntaxError **
                # The 'global' keyword declares that for the entire scope of this 'if st.button' block,
                # 'total_processed_for_preview' refers to the global variable.
                # It MUST come before any assignment to 'total_processed_for_preview' in this block.
                global total_processed_for_preview 
                total_processed_for_preview = 0 # Reset global counter IMMEDIATELY AFTER global declaration
                
                st.session_state.generation_stage = "preview_generating" 
                st.session_state.preview_html_parts = [] # Clear previous preview HTML
                st.session_state.generated_image_data = {} # Clear old full batch data
                st.session_state.zip_buffer = None # Clear old zip
                st.session_state.download_completed_message = False # Reset download message
                post_download_message_container.empty() # Clear post-download message area

                # Store current settings at the start of this generation attempt
                st.session_state.current_settings_hash_at_generation_start = st.session_state.current_settings_hash
                st.session_state.current_webp_lossless = webp_lossless # Store for img_to_base64

                current_settings_for_processing = {
                    'num_colors': num_colors, 'quant_method': quantize_method,
                    'image_border': image_border_percent_raw, 'swatch_sep': swatch_separator_percent_raw,
                    'indiv_swatch_border': individual_swatch_border_percent_raw,
                    'border_color': border_color_hex, 'swatch_border_color': swatch_border_color_hex,
                    'swatch_size': swatch_size_percent, 'output_format': output_format,
                    'webp_lossless': webp_lossless
                }
                
                with spinner_container: # Show spinner while generating
                    with st.spinner("Generating previews... please wait."):
                        # Loop through sources to generate previews up to MAX_PREVIEWS_IN_ZONE
                        # total_processed_for_preview is reset above and incremented in process_image_source_and_generate
                        for source in all_image_sources:
                            process_image_source_and_generate(source, selected_positions, current_settings_for_processing, is_preview_generation=True)
                            # Check if preview limit is reached after processing a source (it might generate multiple previews if multiple positions selected)
                            if total_processed_for_preview >= MAX_PREVIEWS_IN_ZONE: 
                                break
                
                st.session_state.generation_stage = "preview_generated"
                st.rerun() # Rerun to update UI based on new state (show previews, update buttons)

    # Display previews if they exist (either just generated or from a previous completed batch)
    if st.session_state.generation_stage in ["preview_generated", "completed", "full_batch_generating"] and st.session_state.preview_html_parts:
        update_preview_zone() # MAX_PREVIEWS_IN_ZONE is the default limit here

    # "Generate Full Batch" Button - Show if previews are generated and there are images
    if st.session_state.generation_stage == "preview_generated" and all_image_sources and selected_positions:
        # If total generations > a certain threshold, show a special button or warning
        if total_possible_generations > 50: # Example threshold
            if generate_full_batch_button_container.button(f"⚠️ Generate Full Batch ({total_possible_generations} images) - This may take time!", key="confirm_generate_full_batch", type="secondary"): 
                st.session_state.full_batch_button_clicked = True
        else:
            if generate_full_batch_button_container.button(f"✅ Generate Full Batch ({total_possible_generations} images)", type="primary", key="generate_full_batch"):
                st.session_state.full_batch_button_clicked = True
        
        if st.session_state.full_batch_button_clicked: # If either full batch button was clicked
            st.session_state.generation_stage = "full_batch_generating"
            st.session_state.generated_image_data = {} # Clear any old data
            st.session_state.zip_buffer = None # Clear old zip
            st.session_state.download_completed_message = False # Reset download message
            post_download_message_container.empty() # Clear post-download message area
            
            # Ensure settings hash is current for this full batch operation
            st.session_state.current_settings_hash_at_generation_start = st.session_state.current_settings_hash
            st.session_state.current_webp_lossless = webp_lossless # Store for saving functions

            current_settings_for_processing = { # Same settings as preview, but for full batch
                'num_colors': num_colors, 'quant_method': quantize_method,
                'image_border': image_border_percent_raw, 'swatch_sep': swatch_separator_percent_raw,
                'indiv_swatch_border': individual_swatch_border_percent_raw,
                'border_color': border_color_hex, 'swatch_border_color': swatch_border_color_hex,
                'swatch_size': swatch_size_percent, 'output_format': output_format,
                'webp_lossless': webp_lossless
            }

            # Use the preloader_and_status_container for messages during full batch
            with preloader_and_status_container:
                st.markdown("<div class='preloader-area'><div class='preloader'></div><div class='preloader-text' id='status-text'>Processing full batch... initializing...</div></div>", unsafe_allow_html=True)
            
            progress_bar = st.progress(0) # Initialize progress bar
            total_generations_done_for_progress = 0 # Counter for progress bar
            
            st.session_state.total_generations_at_start = total_possible_generations # Total items for progress

            # Loop through sources for full batch processing
            for i, source in enumerate(all_image_sources):
                # Update status text for each source file
                status_text_message = f"Processing: {shorten_filename(source['name'])}... ({i+1}/{len(all_image_sources)} files)"
                # This direct markdown update in a loop might be slightly clunky in Streamlit, but functional
                preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><div class='preloader-text'>{status_text_message}</div></div>", unsafe_allow_html=True)

                process_image_source_and_generate(source, selected_positions, current_settings_for_processing, is_preview_generation=False)
                
                # Increment progress based on the number of positions processed for this source
                total_generations_done_for_progress += len(selected_positions)
                progress_val = total_generations_done_for_progress / st.session_state.total_generations_at_start if st.session_state.total_generations_at_start > 0 else 0
                progress_bar.progress(min(progress_val, 1.0)) # Ensure progress doesn't exceed 1.0

            progress_bar.empty() # Clear progress bar after completion
            preloader_and_status_container.success(f"Full batch processed! {len(st.session_state.generated_image_data)} images generated.")
            
            # Prepare ZIP file if images were generated
            if st.session_state.generated_image_data:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for filename, img_bytes_val in st.session_state.generated_image_data.items():
                        zf.writestr(filename, img_bytes_val)
                st.session_state.zip_buffer = zip_buffer.getvalue()
            
            st.session_state.generation_stage = "completed"
            st.session_state.full_batch_button_clicked = False # Reset button click state
            gc.collect() # Final garbage collection after batch processing
            st.rerun() # Rerun to update UI (show download button, etc.)


    # --- Download Buttons and Start Over ---
    if st.session_state.generation_stage == "completed" and st.session_state.zip_buffer:
        download_buttons_container.download_button(
            label=f"📥 Download All as ZIP ({len(st.session_state.generated_image_data)} images)",
            data=st.session_state.zip_buffer,
            file_name=f"color_palette_batch_{time.strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
            on_click=handle_download_click, # Callback to show post-download message
            key="download_zip_button",
            use_container_width=True
        )
        
        # "Start Over" button after generation is completed
        if download_buttons_container.button("🔄 Start Over / Clear All", key="start_over_completed"):
            # Reset relevant session state variables to initial state
            st.session_state.generation_stage = "initial"
            st.session_state.preview_html_parts = []
            st.session_state.generated_image_data = {}
            st.session_state.zip_buffer = None
            st.session_state.current_settings_hash_at_generation_start = None # Important for re-triggering preview
            st.session_state.download_completed_message = False
            st.session_state.image_url_current_input = "" # Clear URL input field
            
            # Increment uploader key to reset file uploader widget
            st.session_state.file_uploader_key = f"file_uploader_{int(st.session_state.file_uploader_key.split('_')[-1]) + 1}"
            
            # Clear UI containers
            preview_container.empty()
            download_buttons_container.empty()
            post_download_message_container.empty()
            preloader_and_status_container.empty()
            generate_full_batch_button_container.empty()
            gc.collect() # Clean up memory
            st.rerun() # Rerun to reflect the reset state

    # Show post-download message if applicable
    if st.session_state.download_completed_message:
        with post_download_message_container:
            st.markdown(f"""
            <div class='post-download-message-container'>
                <p>✅ Your ZIP file should be downloading. Hope you create something amazing!</p>
                <p>If you found this tool useful, consider supporting its development:</p>
                <a href='https://www.buymeacoffee.com/yourusername' target='_blank' class='buy-dev-coffee-button'>☕ Buy the dev a coffee</a>
            </div>
            """, unsafe_allow_html=True)


    # --- Footer & SEO Section ---
    st.markdown("<hr style='margin-top: 40px; margin-bottom: 20px;'>", unsafe_allow_html=True)
    st.markdown("<div class='seo-section'>", unsafe_allow_html=True)
    # (SEO content remains the same, truncated for brevity)
    st.markdown("""
        <h2>Unlock Creative Possibilities with Batch Image Color Palettes</h2>
        <p>Our Free Color Palette Generator is designed for creators, marketers, and designers who need to quickly extract and visualize color schemes from multiple images. Whether you're planning a Pinterest board, designing Instagram content, or developing brand guidelines, this tool streamlines your workflow by automating the color palette generation process.</p>
        
        <div class="seo-columns">
            <div class="seo-column">
                <h3>Why Batch Process Images for Color Palettes?</h3>
                <ul>
                    <li><strong>Time-Saving:</strong> Generate palettes for hundreds of images in minutes, not hours.</li>
                    <li><strong>Consistency:</strong> Maintain a consistent aesthetic across your projects by easily referencing source image colors.</li>
                    <li><strong>Inspiration:</strong> Discover unexpected color combinations hidden within your image libraries.</li>
                    <li><strong>Automation for Social Media:</strong> Perfect for creating visually harmonious posts for Pinterest, Instagram, and other platforms. Quickly generate images with their color palettes attached for engaging content.</li>
                </ul>
            </div>
            <div class="seo-column">
                <h3>Key Features</h3>
                <ul>
                    <li><strong>Multiple Uploads & URL Fetching:</strong> Process local files or images directly from the web.</li>
                    <li><strong>Customizable Palette Layout:</strong> Choose where the color swatches appear (top, bottom, left, right).</li>
                    <li><strong>Adjustable Color Count:</strong> Extract anywhere from 2 to 12 dominant colors.</li>
                    <li><strong>Flexible Styling:</strong> Control border sizes, colors, and swatch appearance.</li>
                    <li><strong>Multiple Output Formats:</strong> Download your generated images as PNG, JPEG, or WEBP.</li>
                    <li><strong>No Login Required:</strong> Free to use, instantly.</li>
                </ul>
            </div>
        </div>

        <h3>How It Works</h3>
        <p>The tool analyzes each uploaded or fetched image to identify its most dominant colors using quantization algorithms (Median Cut or Fast Octree). It then redraws the original image with the extracted color palette displayed in your chosen position and style. You can preview the results and then generate a full batch for download as a ZIP file.</p>

        <h3>Who Is This For?</h3>
        <p>Graphic designers, social media managers, content creators, digital marketers, artists, agencies, and students too. Whether you need a color scheme generator from images for your next campaign or just want to play around with ideas for your mood board — this tool makes it fast and fun.</p>

        <strong>Let your images tell a color story.</strong>
    """, unsafe_allow_html=True)
    
    st.markdown("<h3>Popular Searches We Serve</h3>", unsafe_allow_html=True)
    st.markdown("""
    Want to know what people are searching for when they land here? If you're searching for any of these, you're in the right place:
    <ul>
        <li>free photo to color palette generator online</li>
        <li>batch generate image + color palette post</li>
        <li>Pinterest automation tools for content creation</li>
        <li>Instagram aesthetic post maker with color swatches</li>
        <li>no login color palette generator</li>
        <li>color palette generator for branding and social media</li>
        <li>create palette from multiple images free</li>
    </ul>
    <strong>Try it now and see how fast and easy your next post, board, or brand update can be. Your images already have the colors — SwatchBatch just helps bring them out.</strong>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


except Exception as e: # Top-level exception handler for the entire application
    st.error(f"A critical error occurred in the application: {e}")
    st.exception(e) # This will print the full traceback to the Streamlit interface
    st.warning("An issue was encountered. Some parts of the application might be reset or behave unexpectedly. Please try refreshing the page or simplifying your batch. If the problem persists, consider reducing the number or size of images.")
    # Attempt to reset to a known safe state, though a full page refresh by the user might be better
    st.session_state.generation_stage = "initial"
    st.session_state.current_settings_hash_at_generation_start = None 
    st.session_state.download_completed_message = False
    # Potentially clear other states if they could be corrupted and lead to further errors
    st.session_state.preview_html_parts = []
    st.session_state.generated_image_data = {}
    st.session_state.zip_buffer = None
    gc.collect() # Attempt to free memory


import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import numpy as np
import io
import zipfile
import base64
import sys
import os
import time

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("Color Swatch Generator")

# --- Initialize Session State ---
# Use session state to manage the generation process stages
if 'generation_stage' not in st.session_state:
    st.session_state.generation_stage = "initial" # Stages: "initial", "preview_generated", "full_batch_generating", "completed"
if 'preview_html_parts' not in st.session_state:
    st.session_state.preview_html_parts = []
if 'generated_image_data' not in st.session_state:
    # Store image data as {filename: bytes} for efficient access
    st.session_state.generated_image_data = {}
if 'zip_buffer' not in st.session_state:
    st.session_state.zip_buffer = None
if 'total_generations_at_start' not in st.session_state:
    st.session_state.total_generations_at_start = 0
if 'current_settings_hash' not in st.session_state:
    st.session_state.current_settings_hash = None
if 'full_batch_button_clicked' not in st.session_state:
    st.session_state.full_batch_button_clicked = False


# --- Global containers for dynamic content ---
# Container for the "Generating previews..." spinner (can be removed or repurposed)
spinner_container = st.empty() # Keeping for now, might be useful later
# Main container for the previews
preview_container = st.container()
# Container for download buttons (ZIP only now)
download_buttons_container = st.container()
# Container for the animated preloader and status text
preloader_and_status_container = st.empty()
# Container for the "Generate Full Batch" button
generate_full_batch_button_container = st.empty()
# Container for displaying image resize messages
resize_message_container = st.empty()


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

    /* Styles for the preview zone */
    #preview-zone {
        display: flex;
        flex-wrap: nowrap; /* Prevents wrapping, enables scrolling */
        overflow-x: auto; /* Enables horizontal scrolling */
        gap: 20px;        /* Adjusted gap between preview items */
        padding: 20px;    /* Inner padding for the preview zone */
        border-radius: 8px;
        min-height: 250px; /* Ensure it has some height even when empty */
        align-items: flex-start; /* Align items to the top */
        margin-bottom: 20px; /* Space below the preview zone */
        background: #ffffff; /* Preview background is white */
        border: 1px solid #e0e0e0; /* Add a border to the preview container */
    }

    /* Styles for individual preview items */
    .preview-item {
        flex: 0 0 auto; /* Items won't grow or shrink */
        display: flex; /* Use flexbox for internal layout */
        flex-direction: column; /* Stack name, image, link vertically */
        align-items: center; /* Center content horizontally */
        text-align: center;
        width: 220px; /* Increased width for each preview item */
        box-shadow: 0 4px 12px rgba(0,0,0,0.15); /* Subtle shadow */
        padding: 10px; /* Inner padding for the item */
        border-radius: 8px;
        background: #f0f0f0; /* Preview item background is light gray */
        border: 1px solid #e0e0e0;
    }

    .preview-item img {
        width: 100%; /* Image takes full available width within .preview-item */
        height: auto;     /* Maintain aspect ratio */
        border-radius: 4px; /* Adjusted image border radius */
        margin-bottom: 8px; /* Space below the image */
        object-fit: contain; /* Scale image to fit container while maintaining aspect ratio */
        max-height: 180px; /* Limit image height to keep preview items consistent */
    }

    .preview-item-name {
        font-size: 12px;
        margin-bottom: 5px;
        color: #333;
        word-break: break_all; /* Break long filenames */
        height: 30px; /* Give it a fixed height to prevent layout shifts */
        overflow: hidden;
        width: 100%; /* Ensure name takes full width */
        text-overflow: ellipsis; /* Add ellipsis for long names */
        white-space: nowrap; /* Prevent wrapping */
    }

    /* Style for the new download link */
    .download-link {
        font-size: 10px;
        color: #888; /* Gray color */
        text-decoration: none; /* Remove underline */
        margin-top: 5px; /* Space above the link */
        /* Added to prevent text wrapping */
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max_width: 100%; /* Ensure it respects the parent width */
        display: block; /* Ensure text-overflow works */
    }

    .download-link:hover {
        text-decoration: underline; /* Underline on hover */
        color: #555;
    }

    /* Add some margin below subheaders for better section separation */
    h2 {
        margin_bottom: 0.9rem !important;
    }

    /* Ensure download buttons have some space */
    .stDownloadButton {
        margin_top: 10px;
    }

    /* CSS for the animated preloader and text */
    .preloader-area {
        display: flex;
        align-items: center;
        justify-content: center; /* Center the content */
        margin: 20px auto; /* Center the container */
        min_height: 40px; /* Ensure it has some height */
    }

    .preloader {
        border: 4px solid #f3f3f3; /* Light grey */
        border-top: 4px solid #3498db; /* Blue */
        border-radius: 50%;
        width: 30px;
        height: 30px;
        animation: spin 1s linear infinite;
        margin-right: 15px; /* Space between spinner and text */
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
    /* This targets Streamlit buttons that are given the 'secondary' type or are styled as such by default in some contexts */
    div[data-testid="stButton"] > button[type="button"]:not(:hover):not(:active) { /* More specific selector for the blue button if it's not explicitly secondary */
        /* background-color: #007BFF !important; 
        color: white !important;
        border-color: #007BFF !important; */
        /* Re-evaluate if this selector is needed or if type='secondary' on the button is better */
    }
    /* Ensure the specific blue button is targeted if it's not naturally secondary */
    /* For instance, if its key is 'generate_full_batch_button' */
    /* We can rely on Streamlit's default theming or explicitly set button type to 'primary' or 'secondary' */

    </style>
""", unsafe_allow_html=True)

# --- Utility Functions ---

def shorten_filename(filename, max_len=25, front_chars=10, back_chars=10):
    """Shortens a filename to fit max_len, keeping front_chars and back_chars."""
    if len(filename) > max_len:
        # Find the extension
        name, ext = os.path.splitext(filename)
        # Calculate chars from the back excluding extension
        back_chars_name = max(0, back_chars - len(ext))
        return f"{name[:front_chars]}...{name[-back_chars_name:]}{ext}"
    return filename

def is_valid_image_header(file_bytes):
    """
    Checks the first few bytes of a file against known image format magic bytes.
    Returns the detected format ('jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'ico')
    or None if not recognized.
    """
    # Read the first 12 bytes (sufficient for most common formats)
    header = file_bytes[:12]

    # Common image format magic bytes
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
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE, kmeans=5) # Fallback
            palette = paletted.getpalette()
            if palette is None: return []
            return [tuple(palette[i:i+3]) for i in range(0, min(num_colors * 3, len(palette)), 3)]
        except Exception: return []

# --- Draw Layout Function ---

def draw_layout(image, colors, position, image_border_thickness_px, swatch_separator_thickness_px,
                individual_swatch_border_thickness_px, border_color, swatch_border_color, swatch_size_percent):
    img_w, img_h = image.size
    main_border = image_border_thickness_px
    internal_swatch_border_thickness = individual_swatch_border_thickness_px

    if position in ['top', 'bottom']:
        actual_swatch_size_px = int(img_h * (swatch_size_percent / 100))
    else:
        actual_swatch_size_px = int(img_w * (swatch_size_percent / 100))
    actual_swatch_size_px = max(1, actual_swatch_size_px)

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
    else:
        return image.copy()

    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    canvas.paste(image, (image_paste_x, image_paste_y))
    draw = ImageDraw.Draw(canvas)

    for i, color_tuple in enumerate(colors):
        current_swatch_width = swatch_width
        current_swatch_height = swatch_height
        if position in ['top', 'bottom']:
            if i == len(colors) - 1: current_swatch_width += extra_width_for_last_swatch
            x0 = swatch_x_start + i * swatch_width
            x1 = x0 + current_swatch_width
            y0 = swatch_y_coord
            y1 = swatch_y_coord + actual_swatch_size_px
        else: # 'left' or 'right'
            if i == len(colors) - 1: current_swatch_height += extra_height_for_last_swatch
            y0 = swatch_y_start + i * swatch_height
            y1 = y0 + current_swatch_height
            x0 = swatch_x_coord
            x1 = swatch_x_coord + actual_swatch_size_px
        draw.rectangle([x0, y0, x1, y1], fill=tuple(color_tuple))
        if internal_swatch_border_thickness > 0 and i < len(colors) - 1:
            if position in ['top', 'bottom']:
                draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=internal_swatch_border_thickness)
            else: # 'left' or 'right'
                draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=internal_swatch_border_thickness)

    if main_border > 0:
        draw.line([(0, 0), (canvas_w - 1, 0)], fill=border_color, width=main_border) # Top
        draw.line([(0, canvas_h - 1), (canvas_w - 1, canvas_h - 1)], fill=border_color, width=main_border) # Bottom
        draw.line([(0, 0), (0, canvas_h - 1)], fill=border_color, width=main_border) # Left
        draw.line([(canvas_w - 1, 0), (canvas_w - 1, canvas_h - 1)], fill=border_color, width=main_border) # Right

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

try:
    with col1:
        st.subheader("Upload Images")
        allowed_extensions = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif", "ico"]
        uploaded_files = st.file_uploader("Choose images", accept_multiple_files=True, type=allowed_extensions, key="file_uploader")
        valid_files_after_upload = []
        if uploaded_files:
            allowed_extensions_set = set([f".{ext.lower()}" for ext in allowed_extensions])
            for file_obj in uploaded_files:
                file_name = file_obj.name
                try:
                    file_obj.seek(0); file_bytes_sample = file_obj.read(12); file_obj.seek(0)
                    detected_format = is_valid_image_header(file_bytes_sample)
                    if detected_format is None:
                        st.warning(f"File `{file_name}` header invalid. Skipped.")
                        continue
                    file_extension = os.path.splitext(file_name)[1].lower()
                    if file_extension not in allowed_extensions_set:
                        st.warning(f"`{file_name}` unsupported extension (`{file_extension}`). Processing based on header.")
                    valid_files_after_upload.append(file_obj)
                except Exception as e:
                    st.error(f"Error checking file `{file_name}`: {e}. Skipped.")
                    continue
            uploaded_files = valid_files_after_upload

        st.subheader("Download Options")
        resize_option = st.radio("Resize method", ["Original size", "Scale (%)"], index=0, key="resize_option")
        scale_percent = 100
        if resize_option == "Scale (%)":
            scale_percent = st.slider("Scale percent", 10, 200, 100, key="scale_percent")
        output_format_options = ["JPG", "PNG", "WEBP"]
        output_format = st.selectbox("Output format", output_format_options, key="output_format")
        webp_lossless = False
        if output_format == "WEBP":
            webp_lossless = st.checkbox("Lossless WEBP", value=False, key="webp_lossless", help="Generates larger files, but with better quality.")
        format_map = {"JPG": ("JPEG", "jpg"), "PNG": ("PNG", "png"), "WEBP": ("WEBP", "webp")}
        img_format, extension = format_map[output_format]

    with col2:
        st.subheader("Layout Settings")
        positions = []
        st.write("Swatch position(s) (multiple can be selected):")
        row1_layout, row2_layout = st.columns(2), st.columns(2)
        if row1_layout[0].toggle("Top", value=True, key="pos_top"): positions.append("top")
        if row1_layout[1].toggle("Left", value=True, key="pos_left"): positions.append("left")
        if row2_layout[0].toggle("Bottom", value=True, key="pos_bottom"): positions.append("bottom")
        if row2_layout[1].toggle("Right", key="pos_right"): positions.append("right")
        quant_method_label = st.selectbox("Palette extraction method", ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"], index=0, key="quant_method", help="MEDIANCUT: Good general results. MAXCOVERAGE: Can be slower. FASTOCTREE: Faster.")
        quant_method_map = {"MEDIANCUT": Image.MEDIANCUT, "MAXCOVERAGE": Image.MAXCOVERAGE, "FASTOCTREE": Image.FASTOCTREE}
        quantize_method_selected = quant_method_map[quant_method_label]
        num_colors = st.slider("Number of swatches", 2, 12, 6, key="num_colors")
        swatch_size_percent_val = st.slider("Swatch size (% of image dimension)", 5, 50, 20, key="swatch_size_percent", help="Percentage of image height (for top/bottom) or width (for left/right).")

    with col3:
        st.subheader("Borders")
        image_border_thickness_px_val = st.slider("Image Border Thickness (px)", 0, 200, 0, key="image_border_thickness_px")
        swatch_separator_thickness_px_val = st.slider("Swatch-Image Separator Thickness (px)", 0, 200, 0, key="swatch_separator_thickness_px", help="Thickness of the line separating swatches from the image.")
        individual_swatch_border_thickness_px_val = st.slider("Individual Swatch Border Thickness (px)", 0, 200, 0, key="individual_swatch_border_thickness_px", help="Thickness of lines separating individual swatches.")
        border_color = st.color_picker("Main Border Color", "#FFFFFF", key="border_color")
        swatch_border_color = st.color_picker("Swatch Border Color", "#FFFFFF", key="swatch_border_color")

    current_settings = (
        frozenset([(f.name, f.size) for f in uploaded_files]) if uploaded_files else None, frozenset(positions),
        resize_option, scale_percent, output_format, webp_lossless, quant_method_label, num_colors,
        swatch_size_percent_val, image_border_thickness_px_val, swatch_separator_thickness_px_val,
        individual_swatch_border_thickness_px_val, border_color, swatch_border_color,
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
        resize_message_container.empty()
    st.session_state.current_settings_hash = current_settings_hash

    if uploaded_files and positions:
        total_generations = len(uploaded_files) * len(positions)
        st.session_state.total_generations_at_start = total_generations
        st.markdown("---")
        preview_display_area = preview_container.empty()
        preview_display_area.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True) # Maintain height

        images_to_process = []
        processing_limit = total_generations
        current_processing_count = 0

        if st.session_state.generation_stage == "initial" and total_generations > 10:
            images_to_process = uploaded_files[:6] # Preview first 6 images
            layouts_to_process = positions
            processing_limit = 6 * len(positions) # Limit for preview
        elif st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
            images_to_process = uploaded_files # Full batch
            layouts_to_process = positions

        if st.session_state.generation_stage in ["initial", "full_batch_generating"] or total_generations <= 10:
            preloader_and_status_container.markdown("<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating in progress...</span></div>", unsafe_allow_html=True)
            download_buttons_container.empty() # Clear while generating
            generate_full_batch_button_container.empty()
            resize_message_container.empty()

            individual_preview_html_parts = []
            zip_buffer = io.BytesIO()
            generated_image_data = {}

            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
                for file_idx, uploaded_file_obj in enumerate(images_to_process):
                    if st.session_state.generation_stage == "initial" and current_processing_count >= processing_limit: break
                    file_name = uploaded_file_obj.name
                    try:
                        uploaded_file_bytes = uploaded_file_obj.getvalue()
                        try:
                            img_stream = io.BytesIO(uploaded_file_bytes); image = Image.open(img_stream); image.verify()
                            img_stream = io.BytesIO(uploaded_file_bytes); image = Image.open(img_stream)
                        except (UnidentifiedImageError, Exception) as e:
                            st.warning(f"Cannot open/verify `{file_name}`. Skipped. Error: {e}")
                            current_processing_count += len(layouts_to_process)
                            preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating... {current_processing_count}/{processing_limit}</span></div>", unsafe_allow_html=True)
                            continue
                        w, h = image.size
                        if not (10 <= w <= 10000 and 10 <= h <= 10000):
                            st.warning(f"`{file_name}` unsupported resolution ({w}x{h}). Skipped.")
                            current_processing_count += len(layouts_to_process)
                            preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating... {current_processing_count}/{processing_limit}</span></div>", unsafe_allow_html=True)
                            continue
                        if image.mode not in ("RGB", "L"): image = image.convert("RGB")
                        palette = extract_palette(image, num_colors, quantize_method_selected)

                        for pos_idx, pos in enumerate(layouts_to_process):
                            if st.session_state.generation_stage == "initial" and current_processing_count >= processing_limit: break
                            try:
                                result_img = draw_layout(image.copy(), palette, pos, image_border_thickness_px_val, swatch_separator_thickness_px_val, individual_swatch_border_thickness_px_val, border_color, swatch_border_color, swatch_size_percent_val)
                                if resize_option == "Scale (%)" and scale_percent != 100:
                                    new_w, new_h = int(result_img.width * scale_percent / 100), int(result_img.height * scale_percent / 100)
                                    if new_w > 0 and new_h > 0: result_img = result_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                                    else: st.warning(f"Cannot resize {file_name}_{pos}. Using original size.")
                                img_byte_arr = io.BytesIO()
                                base_name, _ = os.path.splitext(file_name)
                                safe_base_name = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in base_name).rstrip()
                                name_for_file = f"{safe_base_name}_{pos}.{extension}"
                                save_params = {'quality': 95} if img_format == "JPEG" else ({'quality': 85, 'lossless': True} if img_format == "WEBP" and webp_lossless else ({'quality': 85} if img_format == "WEBP" else {}))
                                result_img.save(img_byte_arr, format=img_format, **save_params)
                                img_bytes_for_download = img_byte_arr.getvalue()
                                generated_image_data[name_for_file] = img_bytes_for_download
                                if st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
                                    zipf.writestr(name_for_file, img_bytes_for_download)
                                preview_thumb = result_img.copy(); preview_thumb.thumbnail((200, 200))
                                with io.BytesIO() as buf_disp: preview_thumb.save(buf_disp, format="PNG"); img_b64_disp = base64.b64encode(buf_disp.getvalue()).decode("utf-8")
                                img_b64_down = base64.b64encode(img_bytes_for_download).decode("utf-8")
                                dl_mime = f"image/{extension}"
                                disp_name = shorten_filename(name_for_file)
                                html_item = f"<div class='preview-item'><div class='preview-item-name' title='{name_for_file}'>{disp_name}</div><img src='data:image/png;base64,{img_b64_disp}' alt='{name_for_file}'><a href='data:{dl_mime};base64,{img_b64_down}' download='{name_for_file}' class='download-link'>Download</a></div>"
                                individual_preview_html_parts.append(html_item)
                                current_processing_count += 1
                                preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating... {current_processing_count}/{processing_limit}</span></div>", unsafe_allow_html=True)
                            except Exception as e_layout:
                                st.error(f"Error for {file_name} (pos: {pos}): {e_layout}")
                                current_processing_count += 1 # Increment to avoid stuck loop
                                preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating... {current_processing_count}/{processing_limit}</span></div>", unsafe_allow_html=True)
                    except Exception as e_file:
                        st.error(f"Error processing `{file_name}`: {e_file}. Skipped.")
                        current_processing_count += len(layouts_to_process) # All layouts for this file
                        preloader_and_status_container.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating... {current_processing_count}/{processing_limit}</span></div>", unsafe_allow_html=True)
                        continue
            st.session_state.preview_html_parts = individual_preview_html_parts
            st.session_state.generated_image_data = generated_image_data
            if st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
                zip_buffer.seek(0); st.session_state.zip_buffer = zip_buffer
            preloader_and_status_container.empty()
            if st.session_state.generation_stage == "initial" and total_generations > 10:
                st.session_state.generation_stage = "preview_generated"
            elif st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
                st.session_state.generation_stage = "completed"

        # --- Display Previews ---
        if st.session_state.preview_html_parts:
            preview_display_area.markdown("<div id='preview-zone'>" + "\n".join(st.session_state.preview_html_parts) + "</div>", unsafe_allow_html=True)
        else:
            preview_display_area.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True) # Keep placeholder

        # --- Display "Generate Full Batch" Button ---
        if st.session_state.generation_stage == "preview_generated":
            with generate_full_batch_button_container:
                # MODIFIED: Added Markdown bolding and set type to "primary" for more emphasis
                if st.button("Large batch detected, do Your adjustments and **click here to generate the rest!**", use_container_width=True, key="generate_full_batch_button", type="primary"):
                    st.session_state.generation_stage = "full_batch_generating"
                    st.session_state.full_batch_button_clicked = True
                    st.rerun()
        else:
            generate_full_batch_button_container.empty()

        # --- Display Download Button Logic ---
        with download_buttons_container:
            if st.session_state.generation_stage == "completed" and st.session_state.zip_buffer and st.session_state.zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader + 50: # Check if zip has meaningful content
                st.download_button(
                    label=f"Download All as ZIP ({extension.upper()})",
                    data=st.session_state.zip_buffer,
                    file_name=f"ColorSwatches_{output_format.lower()}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key="download_zip_enabled",
                    disabled=False
                )
            elif st.session_state.generation_stage == "preview_generated": # MODIFIED: Show disabled button after preview
                st.download_button(
                    label=f"Download All as ZIP ({extension.upper()})",
                    data=io.BytesIO(), # Dummy data
                    file_name=f"ColorSwatches_{output_format.lower()}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key="download_zip_disabled_preview",
                    disabled=True,
                    help="Download will be available after the full batch is generated. Adjust settings if needed, then click the blue button above to generate all images."
                )
            elif uploaded_files : # Fallback for initial state with files but no generation yet
                 st.download_button(
                     label=f"Download All as ZIP ({extension.upper()})",
                     data=io.BytesIO(),
                     file_name=f"ColorSwatches_{output_format.lower()}.zip",
                     mime="application/zip",
                     use_container_width=True,
                     key="download_zip_initial_disabled_fallback",
                     disabled=True,
                     help="Select swatch positions and generate images to enable download."
                 )
            else:
                download_buttons_container.empty() # Clear if no relevant state

    else: # No uploaded files or no positions selected
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts = []
        st.session_state.generated_image_data = {}
        st.session_state.zip_buffer = None
        st.session_state.total_generations_at_start = 0
        st.session_state.full_batch_button_clicked = False
        generate_full_batch_button_container.empty()
        resize_message_container.empty()
        preview_container.empty() # Collapse preview area
        download_buttons_container.empty() # Clear download button
        spinner_container.empty()
        preloader_and_status_container.empty()

        if uploaded_files and not positions:
            st.info("Select at least one swatch position to generate previews and images for download.")
            # Show disabled download button if files are uploaded but no positions
            with download_buttons_container:
                st.download_button(
                    label=f"Download All as ZIP ({extension.upper()})",
                    data=io.BytesIO(),
                    file_name=f"ColorSwatches_{output_format.lower()}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key="download_zip_no_pos_disabled",
                    disabled=True,
                    help="Select swatch positions to enable image generation and download."
                )
        elif not uploaded_files:
            st.info("Upload images to get started.")


except Exception as e:
    st.error(f"An unexpected error occurred: {e}")
    st.exception(e)
    st.warning("Resetting application state. Please try again.")
    for key in list(st.session_state.keys()):
        if key not in ['file_uploader_key_reset_count']: # Avoid issues with potential uploader key
            del st.session_state[key]
    # Re-initialize essential states
    st.session_state.generation_stage = "initial"
    st.session_state.preview_html_parts = []
    st.session_state.generated_image_data = {}
    st.session_state.zip_buffer = None
    st.session_state.total_generations_at_start = 0
    st.session_state.current_settings_hash = None
    st.session_state.full_batch_button_clicked = False
    if 'file_uploader_key_reset_count' not in st.session_state: st.session_state.file_uploader_key_reset_count = 0
    st.session_state.file_uploader_key_reset_count += 1 # To help reset file_uploader on next run if needed by changing its key
    st.rerun()

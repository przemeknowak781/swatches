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
        object_fit: contain; /* Scale image to fit container while maintaining aspect ratio */
        max_height: 180px; /* Limit image height to keep preview items consistent */
    }

    .preview-item-name {
        font_size: 12px;
        margin_bottom: 5px;
        color: #333;
        word_break: break_all; /* Break long filenames */
        height: 30px; /* Give it a fixed height to prevent layout shifts */
        overflow: hidden;
        width: 100%; /* Ensure name takes full width */
        text-overflow: ellipsis; /* Add ellipsis for long names */
        white_space: nowrap; /* Prevent wrapping */
    }

    /* Style for the new download link */
    .download-link {
        font_size: 10px;
        color: #888; /* Gray color */
        text-decoration: none; /* Remove underline */
        margin_top: 5px; /* Space above the link */
        /* Added to prevent text wrapping */
        white_space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max_width: 100%; /* Ensure it respects the parent width */
        display: block; /* Ensure text-overflow works */
    }

    .download-link:hover {
        text_decoration: underline; /* Underline on hover */
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
        align_items: center;
        justify_content: center; /* Center the content */
        margin: 20px auto; /* Center the container */
        min_height: 40px; /* Ensure it has some height */
    }

    .preloader {
        border: 4px solid #f3f3f3; /* Light grey */
        border_top: 4px solid #3498db; /* Blue */
        border-radius: 50%;
        width: 30px;
        height: 30px;
        animation: spin 1s linear infinite;
        margin_right: 15px; /* Space between spinner and text */
    }

    .preloader-text {
        font_size: 16px;
        color: #555;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    /* Custom style for the blue "Large batch detected..." button */
    div[data-testid="stButton"] > button[kind="secondary"] {
        background-color: #007BFF !important; /* Blue background */
        color: white !important; /* White text */
        border-color: #007BFF !important; /* Blue border */
    }

    /* Removed strobe effect CSS */
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
    # JPEG: FF D8 FF DB or FF D8 FF E0 or FF D8 FF E1 (EXIF) or FF D8 FF E2 (Canon) etc.
    if header.startswith(b'\xFF\xD8\xFF'):
        return 'jpeg'
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    elif header.startswith(b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A'):
        return 'png'
    # GIF: 47 49 46 38 37 61 or 47 49 46 38 39 61
    elif header.startswith(b'\x47\x49\x46\x38\x37\x61') or header.startswith(b'\x47\x49\x46\x38\x39\x61'):
        return 'gif'
    # BMP: 42 4D
    elif header.startswith(b'\x42\x4D'):
        return 'bmp'
    # TIFF: 49 49 2A 00 or 4D 4D 00 2A
    elif header.startswith(b'\x49\x49\x2A\x00') or header.startswith(b'\x4D\x4D\x00\x2A'):
        return 'tiff'
    # WEBP: 52 49 46 46 ?? ?? ?? ?? 57 45 42 50
    elif header.startswith(b'\x52\x49\x46\x46') and header[8:12] == b'\x57\x45\x42\x50':
        return 'webp'
    # ICO: 00 00 01 00 (ICO) or 00 00 02 00 (CUR)
    elif header.startswith(b'\x00\x00\x01\x00') or header.startswith(b'\x00\x00\x02\x00'):
        return 'ico'

    return None # Not recognized

# --- Color Extraction ---

def extract_palette(image, num_colors=6, quantize_method=Image.MEDIANCUT):
    """Extracts a color palette from the image."""
    img = image.convert("RGB")
    try:
        # Attempt with the selected method
        # Added kmeans for potentially better results, adjust value as needed
        paletted = img.quantize(colors=num_colors, method=quantize_method, kmeans=5)
        palette_full = paletted.getpalette()

        if palette_full is None:
             # Fallback if getpalette returns None immediately
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE, kmeans=5)
            palette_full = paletted.getpalette()
            if palette_full is None:
                 return []

        actual_palette_colors = len(palette_full) // 3
        colors_to_extract = min(num_colors, actual_palette_colors)
        extracted_palette_rgb_values = palette_full[:colors_to_extract * 3]
        colors = [tuple(extracted_palette_rgb_values[i:i+3]) for i in range(0, len(extracted_palette_rgb_values), 3)]
        return colors

    except Exception as e:
        # If the selected method fails, try FASTOCTREE as a fallback
        try:
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE, kmeans=5)
            palette = paletted.getpalette()
            if palette is None: return []
            colors = [tuple(palette[i:i+3]) for i in range(0, min(num_colors * 3, len(palette)), 3)]
            return colors
        except Exception:
            # If fallback also fails, return empty list
            return []

# --- Draw Layout Function ---

def draw_layout(image, colors, position, image_border_thickness_px, swatch_separator_thickness_px,
                individual_swatch_border_thickness_px, border_color, swatch_border_color, swatch_size_percent):
    """Draws the image layout with color swatches using separate border thickness values."""
    # Removed remove_adjacent_border parameter

    img_w, img_h = image.size
    main_border = image_border_thickness_px
    # Use the new slider value for borders *between* individual swatches
    internal_swatch_border_thickness = individual_swatch_border_thickness_px


    # Calculate actual swatch size in pixels based on percentage
    if position in ['top', 'bottom']:
        # Base swatch size on image height for horizontal swatches
        actual_swatch_size_px = int(img_h * (swatch_size_percent / 100))
    else: # 'left', 'right'
        # Base swatch size on image width for vertical swatches
        actual_swatch_size_px = int(img_w * (swatch_size_percent / 100))

    if actual_swatch_size_px <= 0 : # Ensure swatch size is at least 1px if calculated to 0
        actual_swatch_size_px = 1


    if not colors:
        # If no colors extracted, just add the main border if requested
        if main_border > 0:
            canvas = Image.new("RGB", (img_w + 2 * main_border, img_h + 2 * main_border), border_color)
            canvas.paste(image, (main_border, main_border))
            return canvas
        return image.copy() # Return original image if no colors and no border


    swatch_width = 0
    swatch_height = 0
    extra_width_for_last_swatch = 0
    extra_height_for_last_swatch = 0
    swatch_x_start = 0
    swatch_y_start = 0
    swatch_y = 0
    swatch_x = 0
    image_paste_x = main_border
    image_paste_y = main_border

    # Determine canvas size and image paste position based on swatch position
    # Canvas size needs to accommodate image, swatches, main borders, and the separating line thickness
    if position == 'top':
        canvas_h = img_h + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_w = img_w + 2 * main_border
        swatch_y = main_border
        swatch_x_start = main_border
        swatch_total_width = img_w
        if len(colors) > 0:
            swatch_width = swatch_total_width // len(colors)
            extra_width_for_last_swatch = swatch_total_width % len(colors)
        else:
            swatch_width = swatch_total_width # Should not happen if colors is not empty
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
        else:
            swatch_width = swatch_total_width
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
        else:
            swatch_height = swatch_total_height
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
        else:
            swatch_height = swatch_total_height
        image_paste_x = main_border

    else:
        return image.copy() # Should not happen with valid positions

    # Create the canvas with the main border color
    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    # Paste the original image onto the canvas
    canvas.paste(image, (image_paste_x, image_paste_y))

    draw = ImageDraw.Draw(canvas)

    # Draw the color swatches
    for i, color_tuple in enumerate(colors):
        current_swatch_width = swatch_width
        current_swatch_height = swatch_height

        # Adjust last swatch size to fill the remaining space
        if position in ['top', 'bottom']:
            if i == len(colors) - 1:
                current_swatch_width += extra_width_for_last_swatch
            x0 = swatch_x_start + i * swatch_width
            x1 = x0 + current_swatch_width
            y0 = swatch_y
            y1 = swatch_y + actual_swatch_size_px # Use calculated actual_swatch_size_px
        else: # 'left' or 'right'
            if i == len(colors) - 1:
                current_swatch_height += extra_height_for_last_swatch
            y0 = swatch_y_start + i * swatch_height
            y1 = y0 + current_swatch_height
            x0 = swatch_x
            x1 = swatch_x + actual_swatch_size_px # Use calculated actual_swatch_size_px

        # Draw the swatch rectangle
        draw.rectangle([x0, y0, x1, y1], fill=tuple(color_tuple))

        # Draw internal borders between swatches if thickness > 0
        if internal_swatch_border_thickness > 0:
            if position in ['top', 'bottom']:
                # Always draw the right border of the swatch if it's not the last one
                if i < len(colors) - 1:
                    draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=internal_swatch_border_thickness)

            else: # 'left' or 'right'
                # Always draw the bottom border of the swatch if it's not the last one
                if i < len(colors) - 1:
                    draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=internal_swatch_border_thickness)


    # --- Draw Main Border Around the Entire Canvas ---
    if main_border > 0:
        # Define the coordinates for the outer border lines of the entire canvas
        outer_top_border = [(0, 0), (canvas_w - 1, 0)]
        outer_bottom_border = [(0, canvas_h - 1), (canvas_w - 1, canvas_h - 1)]
        outer_left_border = [(0, 0), (0, canvas_h - 1)]
        outer_right_border = [(canvas_w - 1, 0), (canvas_w - 1, canvas_h - 1)]

        # Draw the outer borders using the main border color and thickness
        draw.line(outer_top_border, fill=border_color, width=main_border)
        draw.line(outer_bottom_border, fill=border_color, width=main_border)
        draw.line(outer_left_border, fill=border_color, width=main_border)
        draw.line(outer_right_border, fill=border_color, width=main_border)

    # --- Draw Border Between Swatch Area and Image (with swatch border color and swatch separator thickness) ---
    # This border is always drawn with the swatch_separator_thickness_px and swatch_border_color
    if swatch_separator_thickness_px > 0:
        # Only draw if swatch separator is present
        if position == 'top':
            # Draw the separating line using draw.line
            line_start = (main_border, main_border + actual_swatch_size_px)
            line_end = (main_border + img_w, main_border + actual_swatch_size_px)
            draw.line([line_start, line_end], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'bottom':
            # Draw the separating line using draw.line
            line_start = (main_border, main_border + img_h)
            line_end = (main_border + img_w, main_border + img_h)
            draw.line([line_start, line_end], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'left':
            # Draw the separating line using draw.line
            line_start = (main_border + actual_swatch_size_px, main_border)
            line_end = (main_border + actual_swatch_size_px, main_border + img_h)
            draw.line([line_start, line_end], fill=swatch_border_color, width=swatch_separator_thickness_px)
        elif position == 'right':
            # Draw the separating line using draw.line
            line_start = (main_border + img_w, main_border)
            line_end = (main_border + img_w, main_border + img_h)
            draw.line([line_start, line_end], fill=swatch_border_color, width=swatch_separator_thickness_px)

    return canvas

# --- Input Columns ---
col1, col2, col3 = st.columns(3)

# --- Top-level exception handling ---
try:
    with col1:
        # Revert to standard subheader
        st.subheader("Upload Images")
        # Removed strobe background class from the file uploader container
        # st.markdown('<div class="strobe-background">', unsafe_allow_html=True)
        # Define allowed extensions
        allowed_extensions = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif", "ico"]
        uploaded_files = st.file_uploader(
            "Choose images",
            accept_multiple_files=True,
            type=allowed_extensions, # Use extensions here
            key="file_uploader" # Added a key
        )
        # Removed closing div for strobe background
        # st.markdown('</div>', unsafe_allow_html=True)

        # Filter out files with unsupported extensions and check magic bytes
        valid_files_after_upload = []
        if uploaded_files:
            # Create a set of allowed extensions (lowercase) for efficient checking
            allowed_extensions_set = set([f".{ext.lower()}" for ext in allowed_extensions])
            for file_obj in uploaded_files:
                file_name = file_obj.name # Get file name here for error messages...
                file_bytes = file_obj.read()
                # Check file extension (case-insensitive)
                _, file_extension = os.path.splitext(file_name)
                if file_extension.lower() not in allowed_extensions_set:
                    st.warning(f"File '{file_name}' has an unsupported extension.  It will be skipped.  Supported extensions are: {', '.join(allowed_extensions)}", icon="⚠️")
                    continue  # Skip this file

                # Check magic bytes
                image_format = is_valid_image_header(file_bytes)
                if not image_format:
                    st.warning(f"File '{file_name}' is not a valid image file. It will be skipped.", icon="⚠️")
                    continue  # Skip this file

                valid_files_after_upload.append((file_name, file_bytes))  # Keep both name and bytes

        # Image size options
        st.subheader("Output Options")
        resize_option = st.selectbox("Resize Images", ["No Resize", "Fit to Width", "Fit to Height"], index=0)
        output_scale = st.slider("Scale Output", 50, 200, 100, help="Scale the output image (percent)")
        output_format = st.selectbox("Output Format", ["JPEG", "PNG", "WEBP"], index=0)

    with col2:
        st.subheader("Layout")
        positions = ['top', 'bottom', 'left', 'right']
        position_toggles = {pos: st.toggle(pos.capitalize(), value=False) for pos in positions}
        # Use a single selectbox for quantization method
        quantize_method_name = st.selectbox(
            "Palette Extraction Method",
            ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"],
            index=0,
            help="Choose the color quantization method.  MEDIANCUT is generally best, but FASTOCTREE is faster."
        )
        # Convert selected name back to the PIL constant
        quantize_method_map = {
            "MEDIANCUT": Image.MEDIANCUT,
            "MAXCOVERAGE": Image.MAXCOVERAGE,
            "FASTOCTREE": Image.FASTOCTREE,
        }
        quantize_method = quantize_method_map[quantize_method_name]

        num_colors = st.slider("Number of Colors", 2, 16, 6)
        swatch_size_percent = st.slider("Swatch Size (%)", 1, 50, 15,
                                          help="Size of the color swatches relative to the image dimension")

    with col3:
        st.subheader("Borders")
        image_border_thickness_px = st.slider("Image Border Thickness (px)", 0, 50, 2)
        swatch_separator_thickness_px = st.slider("Swatch Separator Thickness (px)", 0, 10, 2,
                                                    help="Thickness of the border between the image and the swatches")
        individual_swatch_border_thickness_px = st.slider("Individual Swatch Border Thickness (px)", 0, 5, 1,
                                                            help="Thickness of the border around each individual color swatch")
        border_color = st.color_picker("Border Color", "#000000")
        swatch_border_color = st.color_picker("Swatch Border Color", "#888888")

    # --- Main Processing Logic ---
    # Check if settings have changed
    current_settings = {
        'resize_option': resize_option,
        'output_scale': output_scale,
        'output_format': output_format,
        'position_toggles': position_toggles,
        'quantize_method': quantize_method_name,  # Store the name, not the constant
        'num_colors': num_colors,
        'swatch_size_percent': swatch_size_percent,
        'image_border_thickness_px': image_border_thickness_px,
        'swatch_separator_thickness_px': swatch_separator_thickness_px,
        'individual_swatch_border_thickness_px': individual_swatch_border_thickness_px,
        'border_color': border_color,
        'swatch_border_color': swatch_border_color,
        'num_files': len(valid_files_after_upload) # Include number of files in settings
    }
    current_settings_hash = hash(frozenset(current_settings.items()))

    if st.session_state.current_settings_hash is None:
        st.session_state.current_settings_hash = current_settings_hash # Initialize on first run

    if current_settings_hash != st.session_state.current_settings_hash:
        # Settings have changed, reset generation state
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts = []
        st.session_state.generated_image_data = {}
        st.session_state.zip_buffer = None
        st.session_state.total_generations_at_start = 0
        st.session_state.full_batch_button_clicked = False # Reset this too
        st.session_state.current_settings_hash = current_settings_hash # Update hash
        st.rerun() # Force a rerun to clear the UI and start fresh


    # Get selected positions
    selected_positions = [pos for pos, selected in position_toggles.items() if selected]

    if not valid_files_after_upload:
        st.warning("Please upload one or more image files.", icon="⚠️")
    elif not selected_positions:
        st.warning("Please select at least one swatch position (Top, Bottom, Left, Right).", icon="⚠️")
    else:
        # --- Generation Logic ---
        num_files = len(valid_files_after_upload)
        total_generations = num_files * len(selected_positions)
        st.session_state.total_generations_at_start = total_generations # Store this

        if st.session_state.generation_stage == "initial":
            if total_generations > 5:  # Heuristic: If more than 5 total, show the button
                generate_full_batch_button = generate_full_batch_button_container.button(
                    "Generate All Images",
                    on_click=lambda: setattr(st.session_state, 'generation_stage', 'full_batch_generating'),
                    type="secondary" # Use the custom blue button style
                )
                if generate_full_batch_button:
                    st.session_state.full_batch_button_clicked = True
                    st.session_state.generation_stage = "full_batch_generating" # Move to next stage
                    st.rerun() # Force a rerun to show the preloader
            else:
                st.session_state.generation_stage = "full_batch_generating" # Skip preview
                st.rerun()

        if st.session_state.generation_stage in ["full_batch_generating", "completed"]:
            # Use the preloader_and_status_container
            with preloader_and_status_container:
                if st.session_state.generation_stage == "full_batch_generating":
                    st.markdown('<div class="preloader"></div><span class="preloader-text">Generating images...</span>', unsafe_allow_html=True)
                # else: # Removed the else condition, keep the message for completed state

            if st.session_state.generation_stage == "full_batch_generating":
                st.session_state.generated_image_data = {}  # Clear any previous results
                st.session_state.zip_buffer = io.BytesIO() # reset the zip buffer.
                preview_image_count = 0 # Counter for generated images

                for file_index, (file_name, file_bytes) in enumerate(valid_files_after_upload):
                    try:
                        pil_image = Image.open(io.BytesIO(file_bytes))
                        original_image_format = pil_image.format # get the format.
                    except UnidentifiedImageError:
                        st.error(f"Error: File '{file_name}' could not be opened as an image.  It will be skipped.", icon="🔥")
                        continue  # Skip to the next file

                    # Resize if requested *before* generating layouts
                    if resize_option != "No Resize":
                        max_size = (800, 800)  # Or any other appropriate size
                        if resize_option == "Fit to Width":
                            pil_image.thumbnail((max_size[0], pil_image.size[1]), Image.Resampling.LANCZOS)
                        elif resize_option == "Fit to Height":
                            pil_image.thumbnail((pil_image.size[0], max_size[1]), Image.Resampling.LANCZOS)

                        # Show message about resizing
                        resize_message_container.info(f"Image '{file_name}' was resized to {pil_image.size[0]}x{pil_image.size[1]}", icon="ℹ️")

                    for position in selected_positions:
                        try:
                            colors = extract_palette(pil_image, num_colors, quantize_method)
                            generated_image = draw_layout(pil_image, colors, position,
                                                            image_border_thickness_px, swatch_separator_thickness_px,
                                                            individual_swatch_border_thickness_px, border_color, swatch_border_color, swatch_size_percent)

                            # Apply output scaling
                            if output_scale != 100:
                                scale = output_scale / 100
                                new_size = (int(generated_image.width * scale), int(generated_image.height * scale))
                                generated_image = generated_image.resize(new_size, Image.Resampling.LANCZOS)

                            # Save the generated image to a BytesIO object in the target format
                            img_bytes = io.BytesIO()
                            generated_image.save(img_bytes, format=output_format, quality=95) # High quality
                            img_bytes = img_bytes.getvalue() # Get the byte data

                            # Construct a filename
                            base_name, ext = os.path.splitext(file_name)
                            # position added to filename
                            gen_filename = f"{base_name}_{position.capitalize()}.{output_format.lower()}"
                            st.session_state.generated_image_data[gen_filename] = img_bytes

                            # Add to the ZIP archive
                            with zipfile.ZipFile(st.session_state.zip_buffer, 'a', zipfile.ZIP_STORED, allowZip64=True) as zf:
                                zf.writestr(gen_filename, img_bytes) # Use the generated filename

                            # Create a thumbnail for preview (scaled down, max 300x300)
                            thumbnail_size = (300, 300)
                            preview_image = generated_image.copy() # work on a copy
                            preview_image.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
                            preview_img_bytes = io.BytesIO()
                            preview_image.save(preview_img_bytes, format="JPEG", quality=80)  # Use JPEG for previews
                            preview_img_bytes = preview_img_bytes.getvalue()
                            preview_b64 = base64.b64encode(preview_img_bytes).decode('utf-8')

                            # Use the shortened filename for display
                            short_filename = shorten_filename(gen_filename)

                            # Store the preview HTML
                            preview_html = f"""
                                <div class="preview-item">
                                    <img src="data:image/jpeg;base64,{preview_b64}">
                                    <p class="preview-item-name">{short_filename}</p>
                                    <a href="data:file/{output_format.lower()};base64,{base64.b64encode(img_bytes).decode('utf-8')}"
                                       download="{gen_filename}" class="download-link"
                                       >Download {output_format.upper()}</a>
                                </div>
                            """
                            st.session_state.preview_html_parts.append(preview_html)
                            preview_image_count += 1 # Increment

                        except Exception as e:
                            st.error(f"Error processing {file_name} for {position}: {e}", icon="🔥")

                    # Update progress text.
                    generated_count = len(st.session_state.generated_image_data)
                    preloader_and_status_container.markdown(f'<div class="preloader"></div><span class="preloader-text">Generated {generated_count} of {st.session_state.total_generations_at_start} images...</span>', unsafe_allow_html=True)


                # After the loop, update generation stage:
                st.session_state.generation_stage = "completed"
                st.rerun() # Force a refresh to show the previews and download


        if st.session_state.generation_stage == "completed":
            # Display the generated previews
            with preview_container:
                st.markdown('<div id="preview-zone">', unsafe_allow_html=True)
                for html_part in st.session_state.preview_html_parts:
                    st.markdown(html_part, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

            # Download button
            with download_buttons_container:
                if st.session_state.zip_buffer: # Check if the buffer has data
                    st.download_button(
                        label=f"Download All as ZIP ({output_format.upper()})",
                        data=st.session_state.zip_buffer.getvalue(),
                        file_name=f"ColorSwatches_{output_format.lower()}.zip",
                        mime="application/zip",
                        use_container_width=True,
                        key="download_zip_final", # Key changed to prevent re-creation
                        help="Download all generated images as a ZIP archive."
                    )
                else:
                     st.download_button(
                     label=f"Download All as ZIP ({output_format.upper()})",
                     data=io.BytesIO(), # Empty data initially
                     file_name=f"ColorSwatches_{output_format.lower()}.zip",
                     mime="application/zip",
                     use_container_width=True,
                     key="download_zip_initial", # Use a different key for the initial state button
                     disabled=True, # Keep disabled until generation is complete
                     help="Upload images and select swatch positions to enable download." # Tooltip
                 )


except Exception as e:
    # --- Top-level exception handler ---
    st.error(f"An unexpected error occurred during file processing: {e}")
    st.warning("Resetting application state. Please try uploading your files again. If the issue persists with the same files, they might be corrupted or in an unsupported format.")

    # Reset session state to clear any corrupted data and return to a stable state
    st.session_state.generation_stage = "initial"
    st.session_state.preview_html_parts = []
    st.session_state.generated_image_data = {}
    st.session_state.zip_buffer = None
    st.session_state.total_generations_at_start = 0
    st.session_state.full_batch_button_clicked = False

    # Clear the file uploader widget by changing its key
    # This will also clear the uploaded files list
    st.session_state.file_uploader = None

    # Trigger a rerun to restart the script in a clean state
    st.rerun()

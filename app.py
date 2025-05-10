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
        height: auto;       /* Maintain aspect ratio */
        border-radius: 4px; /* Adjusted image border radius */
        margin-bottom: 8px; /* Space below the image */
        object-fit: contain; /* Scale image to fit container while maintaining aspect ratio */
        max-height: 180px; /* Limit image height to keep preview items consistent */
    }

    .preview-item-name {
        font-size: 12px;
        margin-bottom: 5px;
        color: #333;
        word-break: break-all; /* Break long filenames */
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
        max-width: 100%; /* Ensure it respects the parent width */
        display: block; /* Ensure text-overflow works */
    }

    .download-link:hover {
        text-decoration: underline; /* Underline on hover */
        color: #555;
    }

    /* Add some margin below subheaders for better section separation */
    h2 {
        margin-bottom: 0.9rem !important;
    }

    /* Ensure download buttons have some space */
    .stDownloadButton {
        margin-top: 10px;
    }

    /* CSS for the animated preloader and text */
    .preloader-area {
        display: flex;
        align-items: center;
        justify-content: center; /* Center the content */
        margin: 20px auto; /* Center the container */
        min-height: 40px; /* Ensure it has some height */
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
        # Convert hex color string to RGB tuple
        border_color_rgb = tuple(int(border_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        if main_border > 0:
            canvas = Image.new("RGB", (img_w + 2 * main_border, img_h + 2 * main_border), border_color_rgb)
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
    # Convert hex color strings to RGB tuples
    border_color_rgb = tuple(int(border_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color_rgb)
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
            # Convert swatch border color hex string to RGB tuple
            swatch_border_color_rgb = tuple(int(swatch_border_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
            if position in ['top', 'bottom']:
                # Always draw the right border of the swatch if it's not the last one
                if i < len(colors) - 1:
                    draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color_rgb, width=internal_swatch_border_thickness)

            else: # 'left' or 'right'
                # Always draw the bottom border of the swatch if it's not the last one
                if i < len(colors) - 1:
                    draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color_rgb, width=internal_swatch_border_thickness)


    # --- Draw Main Border Around the Entire Canvas ---
    if main_border > 0:
        # Convert main border color hex string to RGB tuple
        border_color_rgb = tuple(int(border_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        # Define the coordinates for the outer border lines of the entire canvas
        # Adjust coordinates slightly to draw the border *around* the canvas, adding to its size
        # This requires the canvas size calculation to already include the border, which it does.
        # Drawing lines at the edges with width=main_border will cover the edge pixels.
        # A more robust way for a true outer border would be to draw rectangles.
        # Let's stick to lines for now but be aware of this nuance.

        # Draw the outer borders using the main border color and thickness
        # Top border
        draw.line([(0, 0), (canvas_w - 1, 0)], fill=border_color_rgb, width=main_border)
        # Bottom border
        draw.line([(0, canvas_h - 1), (canvas_w - 1, canvas_h - 1)], fill=border_color_rgb, width=main_border)
        # Left border
        draw.line([(0, 0), (0, canvas_h - 1)], fill=border_color_rgb, width=main_border)
        # Right border
        draw.line([(canvas_w - 1, 0), (canvas_w - 1, canvas_h - 1)], fill=border_color_rgb, width=main_border)


    # --- Draw Border Between Swatch Area and Image (with swatch border color and swatch separator thickness) ---
    # This border is always drawn with the swatch_separator_thickness_px and swatch_border_color
    if swatch_separator_thickness_px > 0: # Only draw if swatch separator is present
        # Convert swatch border color hex string to RGB tuple
        swatch_border_color_rgb = tuple(int(swatch_border_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        if position == 'top':
            # Draw the separating line using draw.line
            # Corrected end coordinate
            line_start = (main_border, main_border + actual_swatch_size_px)
            line_end = (main_border + img_w, main_border + actual_swatch_size_px)
            draw.line([line_start, line_end], fill=swatch_border_color_rgb, width=swatch_separator_thickness_px)
        elif position == 'bottom':
             # Draw the separating line using draw.line
            line_start = (main_border, main_border + img_h)
            line_end = (main_border + img_w, main_border + img_h)
            draw.line([line_start, line_end], fill=swatch_border_color_rgb, width=swatch_separator_thickness_px)
        elif position == 'left':
             # Draw the separating line using draw.line
            line_start = (main_border + actual_swatch_size_px, main_border)
            line_end = (main_border + actual_swatch_size_px, main_border + img_h)
            draw.line([line_start, line_end], fill=swatch_border_color_rgb, width=swatch_separator_thickness_px)
        elif position == 'right':
             # Draw the separating line using draw.line
            line_start = (main_border + img_w, main_border)
            line_end = (main_border + img_w, main_border + img_h)
            draw.line([line_start, line_end], fill=swatch_border_color_rgb, width=swatch_separator_thickness_px)


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
                file_name = file_obj.name # Get file name here for error messages
                # --- Start broad exception handling for file access/initial processing ---
                try:
                    # Read the full file content once
                    file_bytes = file_obj.getvalue()

                    # Attempt to open and verify the image using PIL
                    try:
                        image_stream = io.BytesIO(file_bytes)
                        image = Image.open(image_stream)
                        image.verify() # Verify image integrity
                        # Re-open the image stream as verify might close it
                        image_stream.seek(0)
                        image = Image.open(image_stream)

                    except (UnidentifiedImageError, Exception) as e:
                         st.warning(f"Could not open or verify image file: `{file_name}`. It might be corrupted or not a valid image file. Skipped.")
                         continue # Skip to the next file


                    # Further checks after successful opening
                    w, h = image.size
                    if not (10 <= w <= 10000 and 10 <= h <= 10000):
                        st.warning(f"`{file_name}` has an unsupported dimension ({w}x{h}). Dimensions must be between 10x10 and 10000x10000 pixels. Skipped.")
                        continue # Skip this file

                    # Check magic bytes after reading the full content
                    detected_format = is_valid_image_header(file_bytes)
                    if detected_format is None:
                         st.warning(f"File `{file_name}` does not appear to be a valid or supported image format based on its header. Skipped.")
                         continue # Skip this file


                    file_extension = os.path.splitext(file_name)[1].lower()
                    # Check against the allowed extensions list (for user message clarity)
                    if file_extension not in allowed_extensions_set:
                         st.warning(f"`{file_name}` has an unusual or unsupported extension (`{file_extension}`). Allowed extensions are: {', '.join(sorted(list(allowed_extensions_set)))}. Processing based on detected header, but unexpected behavior may occur.")

                    valid_files_after_upload.append(file_obj)

                except Exception as e:
                     # Catch any error during initial file object access or header check
                     st.error(f"An error occurred while performing initial check on file `{file_name}`: {e}. This file will be skipped.")
                     continue # Skip to the next file in the loop
                # --- End broad exception handling ---

            uploaded_files = valid_files_after_upload # Update uploaded_files to only include valid ones


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

        format_map = {
            "JPG": ("JPEG", "jpg"),
            "PNG": ("PNG", "png"),
            "WEBP": ("WEBP", "webp")
        }
        img_format, extension = format_map[output_format]


    with col2:
        st.subheader("Layout Settings")
        positions = []
        st.write("Swatch position(s) (multiple can be selected):")

        # Use columns for layout toggles
        row1_layout = st.columns(2)
        row2_layout = st.columns(2)

        # Turn on Left and Top by default
        if row1_layout[0].toggle("Top", value=True, key="pos_top"): positions.append("top")
        if row1_layout[1].toggle("Left", value=True, key="pos_left"): positions.append("left")
        # Default 'bottom' to True as requested
        if row2_layout[0].toggle("Bottom", value=True, key="pos_bottom"): positions.append("bottom")
        if row2_layout[1].toggle("Right", key="pos_right"): positions.append("right")


        quant_method_label = st.selectbox(
            "Palette extraction method",
            ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"],
            index=0, key="quant_method",
            help="MEDIANCUT: Good general results. MAXCOVERAGE: Can be slower. FASTOCTREE: Faster."
        )
        quant_method_map = {"MEDIANCUT": Image.MEDIANCUT, "MAXCOVERAGE": Image.MAXCOVERAGE, "FASTOCTREE": Image.FASTOCTREE}
        quantize_method_selected = quant_method_map[quant_method_label]

        num_colors = st.slider("Number of swatches", 2, 12, 6, key="num_colors")

        # Swatch size as a percentage of image dimension
        swatch_size_percent_val = st.slider("Swatch size (% of image dimension)", 5, 50, 20, key="swatch_size_percent", help="Percentage of image height (for top/bottom) or width (for left/right).")


    with col3:
        st.subheader("Borders")

        # Separate sliders for image border, swatch-image separator, and individual swatch borders
        image_border_thickness_px_val = st.slider("Image Border Thickness (px)", 0, 200, 0, key="image_border_thickness_px")
        swatch_separator_thickness_px_val = st.slider("Swatch-Image Separator Thickness (px)", 0, 200, 0, key="swatch_separator_thickness_px", help="Thickness of the line separating swatches from the image.")
        # New slider for individual swatch borders
        individual_swatch_border_thickness_px_val = st.slider("Individual Swatch Border Thickness (px)", 0, 200, 0, key="individual_swatch_border_thickness_px", help="Thickness of lines separating individual swatches.")


        border_color = st.color_picker("Main Border Color", "#FFFFFF", key="border_color")
        swatch_border_color = st.color_picker("Swatch Border Color", "#FFFFFF", key="swatch_border_color") # Default color changed to white

        # Removed the "Align swatches with image edge" checkbox
        # remove_adjacent_border = st.checkbox("Align swatches with image edge", value=True, key="remove_adjacent_border")


    # --- Check for settings change to reset state ---
    # Create a hash of current relevant settings
    current_settings = (
        frozenset([(f.name, f.size) for f in uploaded_files]) if uploaded_files else None,
        frozenset(positions),
        resize_option,
        scale_percent,
        output_format,
        webp_lossless,
        quant_method_label,
        num_colors,
        swatch_size_percent_val,
        image_border_thickness_px_val,
        swatch_separator_thickness_px_val,
        individual_swatch_border_thickness_px_val,
        border_color,
        swatch_border_color,
        # Removed remove_adjacent_border from hash
    )
    current_settings_hash = hash(current_settings)

    # If settings have changed, reset the generation stage and button clicked state
    if st.session_state.current_settings_hash is not None and st.session_state.current_settings_hash != current_settings_hash:
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts = []
        st.session_state.generated_image_data = {}
        st.session_state.zip_buffer = None
        st.session_state.total_generations_at_start = 0 # Reset total count
        st.session_state.full_batch_button_clicked = False # Reset button clicked state
        generate_full_batch_button_container.empty() # Clear the button if settings change
        resize_message_container.empty() # Clear resize messages on settings change


    st.session_state.current_settings_hash = current_settings_hash # Update the stored hash


    # --- Main Generation Logic ---
    if uploaded_files and positions:
        total_generations = len(uploaded_files) * len(positions)
        st.session_state.total_generations_at_start = total_generations # Store total for later reference

        st.markdown("---")
        # Removed the "Previews" subheader
        # st.subheader("Previews")

        # Initialize preview_display_area here unconditionally
        preview_display_area = preview_container.empty()

        # Determine which images/layouts to generate based on the stage
        images_to_process = []
        if st.session_state.generation_stage == "initial" and total_generations > 10:
            # Process only the first 6 for preview
            images_to_process = uploaded_files[:6]
            layouts_to_process = positions # Process all selected positions for the first 6 images
            processing_limit = min(6 * len(positions), total_generations) # Limit total generations for preview
            current_processing_count = 0

        elif st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
             # Process all images and layouts
            images_to_process = uploaded_files
            layouts_to_process = positions
            processing_limit = total_generations # No limit for full batch or small batches
            current_processing_count = 0 # Reset count for full batch display


        # Display preloader and status text if generating
        if st.session_state.generation_stage in ["initial", "full_batch_generating"] or total_generations <= 10:
            preloader_and_status_container.markdown("""
                <div class='preloader-area'>
                    <div class='preloader'></div>
                    <span class='preloader-text'>Generating in progress...</span>
                </div>
            """, unsafe_allow_html=True)

            # Clear previous previews and buttons before generating
            preview_display_area.empty() # Clear preview area
            download_buttons_container.empty()
            generate_full_batch_button_container.empty() # Clear button if it was there
            resize_message_container.empty() # Clear previous resize messages


            # --- Generation Loop ---
            individual_preview_html_parts = []
            zip_buffer = io.BytesIO()
            generated_image_data = {}

            # Use compresslevel=0 (ZIP_STORED) for speed, as images are already compressed.
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
                for file_idx, uploaded_file_obj in enumerate(images_to_process):
                    file_name = uploaded_file_obj.name

                    # --- Start Exception Handling for File Processing ---
                    try:
                        uploaded_file_bytes = uploaded_file_obj.getvalue() # Use uploaded_file_obj here

                        # Attempt to open and verify the image using PIL
                        try:
                            image_stream_for_verify = io.BytesIO(uploaded_file_bytes)
                            image = Image.open(image_stream_for_verify)
                            image.verify() # Verify image integrity
                            # Re-open the image stream as verify might close it
                            image_stream_for_load = io.BytesIO(uploaded_file_bytes)
                            image = Image.open(image_stream_for_load)


                        except (UnidentifiedImageError, Exception) as e:
                             st.warning(f"Could not open or verify image file: `{file_name}`. It might be corrupted or not a valid image file. Skipped.")
                             current_processing_count += len(layouts_to_process) # Increment count for skipped file
                             # Update preloader text for skipped file
                             preloader_and_status_container.markdown(f"""
                                 <div class='preloader-area'>
                                     <div class='preloader'></div>
                                     <span class='preloader-text'>Generating in progress... {current_processing_count}/{processing_limit}</span>
                                 </div>
                             """, unsafe_allow_html=True)
                             continue # Skip to the next file


                        # Further checks after successful opening
                        w, h = image.size
                        if not (10 <= w <= 10000 and 10 <= h <= 10000):
                            st.warning(f"`{file_name}` has an unsupported dimension ({w}x{h}). Dimensions must be between 10x10 and 10000x10000 pixels. Skipped.")
                            current_processing_count += len(layouts_to_process) # Increment count for skipped file
                            # Update preloader text for skipped file
                            preloader_and_status_container.markdown(f"""
                                <div class='preloader-area'>
                                    <div class='preloader'></div>
                                    <span class='preloader-text'>Generating in progress... {current_processing_count}/{processing_limit}</span>
                                </div>
                            """, unsafe_allow_html=True)
                            continue # Skip this file

                        # Check magic bytes after reading the full content
                        detected_format = is_valid_image_header(uploaded_file_bytes)
                        if detected_format is None:
                             st.warning(f"File `{file_name}` does not appear to be a valid or supported image format based on its header. Skipped.")
                             current_processing_count += len(layouts_to_process) # Increment count for skipped file
                             # Update preloader text for skipped file
                             preloader_and_status_container.markdown(f"""
                                 <div class='preloader-area'>
                                     <div class='preloader'></div>
                                     <span class='preloader-text'>Generating in progress... {current_processing_count}/{processing_limit}</span>
                                 </div>
                             """, unsafe_allow_html=True)
                             continue # Skip to the next file


                        file_extension = os.path.splitext(file_name)[1].lower()
                        # Check against the allowed extensions list (for user message clarity)
                        if file_extension not in allowed_extensions_set:
                             st.warning(f"`{file_name}` has an unusual or unsupported extension (`{file_extension}`). Allowed extensions are: {', '.join(sorted(list(allowed_extensions_set)))}. Processing based on detected header, but unexpected behavior may occur.")


                        # Extract colors
                        colors = extract_palette(image, num_colors=num_colors, quantize_method=quantize_method_selected)

                        if not colors:
                            st.warning(f"Could not extract colors from `{file_name}`. Skipped.")
                            current_processing_count += len(layouts_to_process) # Increment count for skipped file
                            # Update preloader text for skipped file
                            preloader_and_status_container.markdown(f"""
                                <div class='preloader-area'>
                                    <div class='preloader'></div>
                                    <span class='preloader-text'>Generating in progress... {current_processing_count}/{processing_limit}</span>
                                </div>
                            """, unsafe_allow_html=True)
                            continue # Skip to the next file


                        for position in layouts_to_process:
                            current_processing_count += 1 # Increment for each generated image

                            # Generate the modified image
                            modified_image = draw_layout(
                                image.copy(), # Pass a copy to avoid modifying the original image object
                                colors,
                                position,
                                image_border_thickness_px_val,
                                swatch_separator_thickness_px_val,
                                individual_swatch_border_thickness_px_val,
                                border_color, # Pass hex string, conversion happens in draw_layout
                                swatch_border_color, # Pass hex string, conversion happens in draw_layout
                                swatch_size_percent_val
                            )

                            # Resize if requested
                            if resize_option == "Scale (%)" and scale_percent != 100:
                                original_size = modified_image.size
                                new_width = int(original_size[0] * scale_percent / 100)
                                new_height = int(original_size[1] * scale_percent / 100)
                                # Use LANCZOS filter for high-quality downsampling/upsampling
                                modified_image = modified_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                                resize_message_container.info(f"Resized '{file_name}' ({position}) from {original_size[0]}x{original_size[1]} to {new_width}x{new_height} ({scale_percent}%).")


                            # Save the generated image to a bytes buffer
                            img_byte_arr = io.BytesIO()
                            save_params = {}
                            if img_format == "JPEG":
                                save_params['quality'] = 90 # Default JPEG quality
                            elif img_format == "WEBP":
                                save_params['lossless'] = webp_lossless

                            # Ensure image is in RGB mode for JPEG/WEBP if it's not already
                            if img_format in ["JPEG", "WEBP"] and modified_image.mode != 'RGB':
                                modified_image = modified_image.convert('RGB')
                            # Ensure image is in RGBA mode for PNG if it has an alpha channel
                            elif img_format == "PNG" and modified_image.mode != 'RGBA' and 'A' in modified_image.getbands():
                                modified_image = modified_image.convert('RGBA')


                            modified_image.save(img_byte_arr, format=img_format, **save_params)
                            img_byte_arr = img_byte_arr.getvalue()

                            # Generate filename for the output image
                            base_name = os.path.splitext(file_name)[0]
                            output_filename = f"{base_name}_{position}.{extension}"

                            # Store image data for ZIP
                            generated_image_data[output_filename] = img_byte_arr

                            # Add to ZIP file immediately if generating full batch or small batch
                            if st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
                                zipf.writestr(output_filename, img_byte_arr)


                            # Generate HTML for preview (only for the first few images if total > 10)
                            if st.session_state.generation_stage == "initial" and total_generations > 10 and current_processing_count <= processing_limit:
                                img_base64 = base64.b64encode(img_byte_arr).decode()
                                data_url = f"data:image/{extension};base64,{img_base64}"
                                short_name = shorten_filename(output_filename)
                                individual_preview_html_parts.append(f"""
                                    <div class='preview-item'>
                                        <div class='preview-item-name' title='{output_filename}'>{short_name}</div>
                                        <img src='{data_url}' alt='{output_filename} Preview'>
                                        <a href='{data_url}' download='{output_filename}' class='download-link'>Download</a>
                                    </div>
                                """)

                            # Update preloader text
                            preloader_and_status_container.markdown(f"""
                                <div class='preloader-area'>
                                    <div class='preloader'></div>
                                    <span class='preloader-text'>Generating in progress... {current_processing_count}/{processing_limit}</span>
                                </div>
                            """, unsafe_allow_html=True)


                    except Exception as e:
                        # Catch any error during processing of a single file/layout combination
                        st.error(f"An error occurred while processing file `{file_name}` with layout `{position}`: {e}. This combination will be skipped.")
                        current_processing_count += 1 # Increment count even for failed generation
                         # Update preloader text for skipped combination
                        preloader_and_status_container.markdown(f"""
                            <div class='preloader-area'>
                                <div class='preloader'></div>
                                <span class='preloader-text'>Generating in progress... {current_processing_count}/{processing_limit}</span>
                            </div>
                        """, unsafe_allow_html=True)
                        continue # Skip to the next layout for this file, or next file


            # --- End of Generation Loop ---

            # After the loop, display previews or handle full batch completion
            if st.session_state.generation_stage == "initial" and total_generations > 10:
                # Display the generated previews
                if individual_preview_html_parts:
                    preview_html = "<div id='preview-zone'>" + "".join(individual_preview_html_parts) + "</div>"
                    preview_display_area.markdown(preview_html, unsafe_allow_html=True)
                    preloader_and_status_container.empty() # Remove preloader after previews are shown

                    # Display the "Generate Full Batch" button
                    with generate_full_batch_button_container:
                        st.warning(f"Large batch detected ({total_generations} images). Showing first {processing_limit} previews.")
                        if st.button(f"Generate Full Batch ({total_generations} images)", type="secondary"):
                            st.session_state.generation_stage = "full_batch_generating"
                            st.session_state.full_batch_button_clicked = True
                            st.rerun() # Rerun the script to start full batch generation
                else:
                     preloader_and_status_container.empty() # Remove preloader if no previews generated
                     st.info("No previews could be generated with the current settings and files.")


            elif st.session_state.generation_stage == "full_batch_generating" or total_generations <= 10:
                # Generation is complete (either full batch or small batch)
                st.session_state.generation_stage = "completed"
                st.session_state.generated_image_data = generated_image_data # Store all generated data
                st.session_state.zip_buffer = zip_buffer # Store the completed zip buffer

                preloader_and_status_container.empty() # Remove preloader

                # Display download button
                if generated_image_data:
                    zip_buffer.seek(0) # Rewind the buffer to the beginning
                    with download_buttons_container:
                        st.success(f"Generation complete! {len(generated_image_data)} images generated.")
                        st.download_button(
                            label=f"Download All ({len(generated_image_data)} images) as ZIP",
                            data=zip_buffer,
                            file_name="color_swatches.zip",
                            mime="application/zip"
                        )
                else:
                    st.warning("No images were successfully generated with the current settings and files.")

            # If the full batch button was clicked, and we are not yet generating, trigger rerun
            if st.session_state.full_batch_button_clicked and st.session_state.generation_stage != "full_batch_generating":
                 st.session_state.full_batch_button_clicked = False # Reset the flag
                 st.rerun() # Rerun to enter the full_batch_generating stage


    elif uploaded_files and not positions:
         st.info("Please select at least one swatch position to generate swatches.")
         # Clear containers if files are uploaded but no positions are selected
         preview_container.empty()
         download_buttons_container.empty()
         preloader_and_status_container.empty()
         generate_full_batch_button_container.empty()
         resize_message_container.empty()

    elif not uploaded_files:
         # Clear containers if no files are uploaded
         preview_container.empty()
         download_buttons_container.empty()
         preloader_and_status_container.empty()
         generate_full_batch_button_container.empty()
         resize_message_container.empty()
         st.session_state.generation_stage = "initial" # Reset stage if files are removed
         st.session_state.preview_html_parts = []
         st.session_state.generated_image_data = {}
         st.session_state.zip_buffer = None
         st.session_state.total_generations_at_start = 0
         st.session_state.full_batch_button_clicked = False


except Exception as e:
    # Catch any unexpected top-level errors
    st.error(f"An unexpected error occurred: {e}")
    # Optionally, display traceback for debugging
    # import traceback
    # st.exception(e)

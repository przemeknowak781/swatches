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

# --- Global containers for dynamic content ---
# Container for the "Generating previews..." spinner (can be removed or repurposed)
spinner_container = st.empty() # Keeping for now, might be useful later
# Main container for the previews
preview_container = st.container()
# Container for download buttons (ZIP only now)
download_buttons_container = st.container()
# Container for the animated preloader and status text
preloader_and_status_container = st.empty()

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
        background: #ffffff;
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

def draw_layout(image, colors, position, border_thickness_px, swatch_border_thickness_percent,
                border_color, swatch_border_color, swatch_size_percent, remove_adjacent_border):
    """Draws the image layout with color swatches. Swatch size and border are percentages."""

    img_w, img_h = image.size
    border = border_thickness_px # Already in pixels

    # Calculate actual swatch size in pixels based on percentage
    if position in ['top', 'bottom']:
        # Base swatch size on image height for horizontal swatches
        actual_swatch_size_px = int(img_h * (swatch_size_percent / 100))
    else: # 'left', 'right'
        # Base swatch size on image width for vertical swatches
        actual_swatch_size_px = int(img_w * (swatch_size_percent / 100))

    if actual_swatch_size_px <= 0 : # Ensure swatch size is at least 1px if calculated to 0
        actual_swatch_size_px = 1

    # Calculate swatch border thickness in pixels based on percentage of swatch size
    swatch_border_thickness_px = int(actual_swatch_size_px * (swatch_border_thickness_percent / 100))
    if swatch_border_thickness_px < 1 and swatch_border_thickness_percent > 0:
        swatch_border_thickness_px = 1 # Ensure at least 1px if percentage is > 0

    if not colors:
        # If no colors extracted, just add the border if requested
        if border > 0:
            canvas = Image.new("RGB", (img_w + 2 * border, img_h + 2 * border), border_color)
            canvas.paste(image, (border, border))
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
    swatch_area_x0 = 0
    swatch_area_y0 = 0
    swatch_area_x1 = 0
    swatch_area_y1 = 0


    # Determine canvas size and image paste position based on swatch position
    if position == 'top':
        canvas_h = img_h + actual_swatch_size_px + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, actual_swatch_size_px + border))
        swatch_y = border
        swatch_x_start = border
        swatch_total_width = img_w
        if len(colors) > 0:
            swatch_width = swatch_total_width // len(colors)
            extra_width_for_last_swatch = swatch_total_width % len(colors)
        else:
            swatch_width = swatch_total_width # Should not happen if colors is not empty
        # Swatch area coordinates for inner borders relative to canvas
        swatch_area_x0 = border
        swatch_area_y0 = border
        swatch_area_x1 = border + img_w
        swatch_area_y1 = border + actual_swatch_size_px


    elif position == 'bottom':
        canvas_h = img_h + actual_swatch_size_px + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, border))
        swatch_y = border + img_h
        swatch_x_start = border
        swatch_total_width = img_w
        if len(colors) > 0:
            swatch_width = swatch_total_width // len(colors)
            extra_width_for_last_swatch = swatch_total_width % len(colors)
        else:
            swatch_width = swatch_total_width
        # Swatch area coordinates for inner borders relative to canvas
        swatch_area_x0 = border
        swatch_area_y0 = border + img_h
        swatch_area_x1 = border + img_w
        swatch_area_y1 = border + img_h + actual_swatch_size_px


    elif position == 'left':
        canvas_w = img_w + actual_swatch_size_px + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (actual_swatch_size_px + border, border))
        swatch_x = border
        swatch_y_start = border
        swatch_total_height = img_h
        if len(colors) > 0:
            swatch_height = swatch_total_height // len(colors)
            extra_height_for_last_swatch = swatch_total_height % len(colors)
        else:
            swatch_height = swatch_total_height
        # Swatch area coordinates for inner borders relative to canvas
        swatch_area_x0 = border
        swatch_area_y0 = border
        swatch_area_x1 = border + actual_swatch_size_px
        swatch_area_y1 = border + img_h


    elif position == 'right':
        canvas_w = img_w + actual_swatch_size_px + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, border))
        swatch_x = border + img_w
        swatch_y_start = border
        swatch_total_height = img_h
        if len(colors) > 0:
            swatch_height = swatch_total_height // len(colors)
            extra_height_for_last_swatch = swatch_total_height % len(colors)
        else:
            swatch_height = swatch_total_height
        # Swatch area coordinates for inner borders relative to canvas
        swatch_area_x0 = border + img_w
        swatch_area_y0 = border
        swatch_area_x1 = border + img_w + actual_swatch_size_px
        swatch_area_y1 = border + img_h


    else:
        return image.copy() # Should not happen with valid positions


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

        # Draw swatch borders if thickness > 0
        if swatch_border_thickness_px > 0:
            # Define border coordinates
            top_border = [(x0, y0), (x1, y0)]
            bottom_border = [(x0, y1), (x1, y1)]
            left_border = [(x0, y0), (x0, y1)]
            right_border = [(x1, y0), (x1, y1)]

            # Draw borders, potentially skipping adjacent border if remove_adjacent_border is True
            # These borders are *between* swatches or between a swatch and the image edge.
            if not (remove_adjacent_border and position == 'top' and y0 == swatch_area_y0):
                 draw.line(top_border, fill=swatch_border_color, width=swatch_border_thickness_px)

            if not (remove_adjacent_border and position == 'bottom' and y1 == swatch_area_y1):
                 draw.line(bottom_border, fill=swatch_border_color, width=swatch_border_thickness_px)

            if not (remove_adjacent_border and position == 'left' and x0 == swatch_area_x0):
                 draw.line(left_border, fill=swatch_border_color, width=swatch_border_thickness_px)

            if not (remove_adjacent_border and position == 'right' and x1 == swatch_area_x1):
                 draw.line(right_border, fill=swatch_border_color, width=swatch_border_thickness_px)

            # Draw internal borders between swatches
            if position in ['top', 'bottom']:
                if i > 0: # Draw left border for swatches after the first one
                    draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness_px)
            else: # 'left' or 'right'
                if i > 0: # Draw top border for swatches after the first one
                    draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness_px)

    # --- Removed the code to draw the outer border around the entire swatch area ---
    # This section is commented out or removed to achieve the flush look.
    # if border_thickness_px > 0:
    #     # Define the coordinates for the outer border lines of the swatch area
    #     outer_top_border = [(swatch_area_x0, swatch_area_y0), (swatch_area_x1, swatch_area_y0)]
    #     outer_bottom_border = [(swatch_area_x0, swatch_area_y1), (swatch_area_x1, swatch_area_y1)]
    #     outer_left_border = [(swatch_area_x0, swatch_area_y0), (swatch_area_x0, swatch_area_y1)]
    #     outer_right_border = [(swatch_area_x1, swatch_area_y0), (swatch_area_x1, swatch_area_y1)]
    #
    #     # Draw the outer borders using the main border color and thickness
    #     draw.line(outer_top_border, fill=border_color, width=border_thickness_px)
    #     draw.line(outer_bottom_border, fill=border_color, width=border_thickness_px)
    #     draw.line(outer_left_border, fill=border_color, width=border_thickness_px)
    #     draw.line(outer_right_border, fill=border_color, width=border_thickness_px)


    return canvas


# --- Input Columns ---
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Upload Images")
    allowed_types = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif"]
    uploaded_files = st.file_uploader(
        "Choose images",
        accept_multiple_files=True,
        type=allowed_types,
        key="file_uploader" # Added a key
    )

    # Filter out files with unsupported extensions after upload
    valid_files_after_upload = []
    if uploaded_files:
        valid_extensions_tuple = tuple(f".{ext}" for ext in allowed_types)
        for file_obj in uploaded_files:
            # Add a check here for the actual file extension to be safe
            file_extension = os.path.splitext(file_obj.name)[1].lower()
            if file_extension not in [f".{ext}" for ext in allowed_types]:
                 st.warning(f"`{file_obj.name}` has an unsupported extension (`{file_extension}`). Skipped.")
            else:
                valid_files_after_upload.append(file_obj)
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

    if row1_layout[0].toggle("Top", key="pos_top"): positions.append("top")
    if row1_layout[1].toggle("Left", key="pos_left"): positions.append("left")
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

    # Image border thickness as a percentage
    border_thickness_percent = st.slider("Image border thickness (% of width)", 0, 10, 0, key="border_thickness_percent")
    border_color = st.color_picker("Image border color", "#FFFFFF", key="border_color")

    # Swatch border thickness as a percentage of swatch size
    swatch_border_thickness_percent_val = st.slider("Swatch border thickness (% of swatch size)", 0, 50, 5, key="swatch_border_thickness_percent")
    swatch_border_color = st.color_picker("Swatch border color", "#FFFFFF", key="swatch_border_color") # Default color changed to white

    remove_adjacent_border = st.checkbox("Align swatches with image edge", value=True, key="remove_adjacent_border")


# --- Process & Preview ---
if uploaded_files and positions:
    st.markdown("---")
    st.subheader("Previews")

    # Display preloader and status text before processing
    preloader_and_status_container.markdown("""
        <div class='preloader-area'>
            <div class='preloader'></div>
            <span class='preloader-text'>Generating in progress...</span>
        </div>
    """, unsafe_allow_html=True)


    preview_display_area = preview_container.empty() # Prepare the area for previews
    individual_preview_html_parts = []
    zip_buffer = io.BytesIO()

    total_files_to_process = len(uploaded_files) * len(positions)
    processed_files_count = 0

    # Use compresslevel=0 (ZIP_STORED) for speed, as images are already compressed.
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
        for file_idx, uploaded_file_obj in enumerate(uploaded_files):
            file_name = uploaded_file_obj.name

            # --- Start Exception Handling for File Processing ---
            try:
                uploaded_file_bytes = uploaded_file_obj.getvalue()
                image_stream_for_verify = io.BytesIO(uploaded_file_bytes)
                test_image = Image.open(image_stream_for_verify)
                test_image.verify() # Verify image integrity

                image_stream_for_load = io.BytesIO(uploaded_file_bytes)
                image = Image.open(image_stream_for_load)

                # Further checks after successful opening
                w, h = image.size
                if not (10 <= w <= 10000 and 10 <= h <= 10000):
                    st.warning(f"`{file_name}` has an unsupported resolution ({w}x{h}). Skipped.")
                    processed_files_count += len(positions) # Increment count for skipped file
                    # Update preloader text for skipped file
                    preloader_and_status_container.markdown(f"""
                        <div class='preloader-area'>
                            <div class='preloader'></div>
                            <span class='preloader-text'>Generating in progress... {processed_files_count}/{total_files_to_process}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    continue # Skip this file

                # Convert image to RGB if it's not, to ensure compatibility with color drawing
                if image.mode not in ("RGB", "L"):
                     image = image.convert("RGB")

                palette = extract_palette(image, num_colors, quantize_method=quantize_method_selected)

                if not palette:
                    # st.warning(f"Failed to extract palette for `{file_name}`. Skipping swatches.") # Less verbose
                    pass # Continue even if palette extraction fails

                # Calculate image border thickness in pixels based on percentage of image width
                border_px = int(image.width * (border_thickness_percent / 100))


                for pos_idx, pos in enumerate(positions):
                    try:
                        result_img = draw_layout(
                            image.copy(), palette, pos, border_px, swatch_border_thickness_percent_val, # Pass percentage
                            border_color, swatch_border_color, swatch_size_percent_val, remove_adjacent_border
                        )

                        # Apply scaling if selected
                        if resize_option == "Scale (%)" and scale_percent != 100:
                            new_w = int(result_img.width * scale_percent / 100)
                            new_h = int(result_img.height * scale_percent / 100)
                            if new_w > 0 and new_h > 0:
                                result_img = result_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                            else:
                                st.warning(f"Cannot resize {file_name}_{pos}. Using original size.")


                        img_byte_arr = io.BytesIO()
                        base_name, original_extension = os.path.splitext(file_name) # Use os.path.splitext

                        # Create a safe filename for the output
                        safe_base_name = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in base_name).rstrip()
                        name_for_file = f"{safe_base_name}_{pos}.{extension}" # Consistent naming

                        # Save parameters based on output format
                        save_params = {}
                        if img_format == "JPEG": save_params['quality'] = 95 # JPEG quality
                        elif img_format == "WEBP":
                            save_params['quality'] = 85 # Default WEBP quality
                            if webp_lossless:
                                save_params['lossless'] = True
                                save_params['quality'] = 100 # Quality 100 for lossless

                        # Save the full-size image for download
                        result_img.save(img_byte_arr, format=img_format, **save_params)
                        img_bytes_for_download = img_byte_arr.getvalue()

                        # Add to ZIP file
                        zipf.writestr(name_for_file, img_bytes_for_download)

                        # Create a thumbnail for the preview
                        preview_img_for_display = result_img.copy()
                        # Resize thumbnail to fit the preview item width, maintaining aspect ratio
                        preview_img_for_display.thumbnail((200, 200)) # Adjusted thumbnail size

                        with io.BytesIO() as buffer_display:
                            # Save preview thumbnail as PNG for consistent display
                            preview_img_for_display.save(buffer_display, format="PNG")
                            img_base64 = base64.b64encode(buffer_display.getvalue()).decode("utf-8")

                        # Encode the full-size image for the download link
                        img_base64_download = base64.b64encode(img_bytes_for_download).decode("utf-8")
                        download_mime_type = f"image/{extension}" # Mime type for the download link

                        # Shorten filename for display
                        display_name = shorten_filename(name_for_file, max_len=25, front_chars=10, back_chars=10)

                        # Construct HTML for individual preview item with download link
                        single_item_html = f"<div class='preview-item'>"
                        single_item_html += f"<div class='preview-item-name' title='{name_for_file}'>{display_name}</div>" # Add full name as title
                        single_item_html += f"<img src='data:image/png;base64,{img_base64}' alt='Preview of {name_for_file}'>"
                        # Add the download link
                        single_item_html += f"<a href='data:{download_mime_type};base64,{img_base64_download}' download='{name_for_file}' class='download-link'>Download</a>"
                        single_item_html += "</div>"

                        individual_preview_html_parts.append(single_item_html)

                        # Update the preview area dynamically
                        current_full_html_content = ("<div id='preview-zone'>" + "\n".join(individual_preview_html_parts) + "</div>")
                        preview_display_area.markdown(current_full_html_content, unsafe_allow_html=True)

                        processed_files_count += 1 # Increment count for successfully processed layout

                        # Update preloader text with progress
                        preloader_and_status_container.markdown(f"""
                            <div class='preloader-area'>
                                <div class='preloader'></div>
                                <span class='preloader-text'>Generating in progress... {processed_files_count}/{total_files_to_process}</span>
                            </div>
                        """, unsafe_allow_html=True)


                    except Exception as e_layout:
                        st.error(f"Error creating layout for {file_name} (pos: {pos}): {e_layout}")
                        processed_files_count += 1 # Increment count even if layout creation fails
                        # Update preloader text with progress
                        preloader_and_status_container.markdown(f"""
                            <div class='preloader-area'>
                                <div class='preloader'></div>
                                <span class='preloader-text'>Generating in progress... {processed_files_count}/{total_files_to_process}</span>
                            </div>
                        """, unsafe_allow_html=True)


            # --- End Exception Handling for File Processing ---
            except UnidentifiedImageError:
                st.warning(f"Could not identify image file: `{file_name}`. Skipped.")
                processed_files_count += len(positions) # Increment count for skipped file
                # Update preloader text for skipped file
                preloader_and_status_container.markdown(f"""
                    <div class='preloader-area'>
                        <div class='preloader'></div>
                        <span class='preloader-text'>Generating in progress... {processed_files_count}/{total_files_to_process}</span>
                    </div>
                """, unsafe_allow_html=True)
                continue # Skip to the next file

            except Exception as e:
                st.error(f"Error processing `{file_name}`: {e}. Skipped.")
                processed_files_count += len(positions) # Increment count for skipped file
                # Update preloader text for skipped file
                preloader_and_status_container.markdown(f"""
                    <div class='preloader-area'>
                        <div class='preloader'></div>
                        <span class='preloader-text'>Generating in progress... {processed_files_count}/{total_files_to_process}</span>
                    </div>
                """, unsafe_allow_html=True)
                continue # Skip to the next file


    zip_buffer.seek(0)

    # Clear spinner after processing is done
    spinner_container.empty()
    # Clear preloader after processing is done
    preloader_and_status_container.empty()

    # --- Download Buttons (Only ZIP now) ---
    with download_buttons_container: # Use the dedicated container
        # Check if there's anything in the zip buffer beyond the header to ensure files were added
        # A minimal zip file header is about 30 bytes, plus directory entries. A safer check is > 100 bytes.
        if zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader + 100:
            st.download_button(
                label=f"Download All as ZIP ({extension.upper()})",
                data=zip_buffer,
                file_name=f"ColorSwatches_{output_format.lower()}.zip",
                mime="application/zip",
                use_container_width=True,
                key="download_zip",
                disabled=False # Enable button after processing
            )
        elif uploaded_files and positions:
             st.warning("No images were generated for the ZIP. Check errors above.")


# --- Initial State/Messages ---
elif uploaded_files and not positions:
    st.info("Select at least one swatch position to generate previews and images for download.")
    # Clear previous previews and buttons if settings change and no positions are selected
    preview_container.empty()
    download_buttons_container.empty()
    spinner_container.empty()
    preloader_and_status_container.empty()

elif not uploaded_files:
    st.info("Upload images to get started.")
    # Clear previews and buttons if no files are uploaded
    preview_container.empty()
    download_buttons_container.empty()
    spinner_container.empty()
    preloader_and_status_container.empty()

# Initially disable the download button if no files are uploaded or positions selected
if not uploaded_files or not positions:
     with download_buttons_container:
         st.download_button(
             label=f"Download All as ZIP ({extension.upper()})",
             data=io.BytesIO(), # Empty data
             file_name=f"ColorSwatches_{output_format.lower()}.zip",
             mime="application/zip",
             use_container_width=True,
             key="download_zip_disabled",
             disabled=True # Keep disabled
         )

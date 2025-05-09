import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import numpy as np # Currently not used, can be removed if not planned for future use
import io
import zipfile
import base64
# import sys # Not actively used for logging here, st.exception is preferred for Streamlit
import os

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("Color Swatch Generator")
st.markdown("<style>h1{margin-bottom: 20px !important;}</style>", unsafe_allow_html=True)

# --- Global containers for dynamic content ---
# Using st.container() for these is good practice for managing dynamic updates.
# However, for the spinner, it's often placed directly before the long operation.
# And for previews/downloads, they are updated after processing.
# Let's refine their usage slightly.
# spinner_container = st.empty() # We'll use the spinner context manager directly
preview_display_area_container = st.container() # For the HTML preview display
download_buttons_container = st.container()

# --- CSS for responsive columns and general styling ---
# The CSS is quite extensive and well-structured for styling.
# No major changes needed here based on the error.
st.markdown(f"""
    <style>
    /* General page and column styling */
    @media (min-width: 768px) {{
        .responsive-columns {{
            display: flex;
            gap: 2rem;
        }}
        .responsive-columns > div {{
            flex: 1;
        }}
    }}
    h2 {{
        margin-bottom: 0.9rem !important;
        margin-top: 1rem !important;
    }}
    .stFileUploader, .stSelectbox, .stSlider, .stRadio, .stColorPicker {{
        margin-bottom: 10px; /* Add some bottom margin to input widgets */
    }}

    /* Styles for the preview zone */
    #preview-zone {{
        display: flex;
        flex-wrap: nowrap;
        overflow-x: auto;
        gap: 25px;
        padding: 20px;
        border-radius: 8px;
        min-height: 290px;
        background-color: #f8f9fa;
        border: 1px dashed #dee2e6;
        margin-top: 10px;
    }}

    /* Styles for individual preview items */
    .preview-item {{
        position: relative;
        flex: 0 0 200px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        padding: 12px;
        border-radius: 8px;
        background: #ffffff;
        border: 1px solid #e0e0e0;
        transition: box-shadow 0.3s ease;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }}
    .preview-item:hover {{
        box-shadow: 0 6px 16px rgba(0,0,0,0.15);
    }}
    .preview-item img {{
        width: 100%;
        max-width: 176px;
        height: auto;
        border-radius: 4px;
        margin-bottom: 8px;
        align-self: center;
    }}
    .preview-item-name {{
        font-size: 12px;
        margin-bottom: 5px;
        color: #333;
        word-break: break-all;
        height: 30px;
        overflow: hidden;
        line-height: 1.3;
    }}

    /* Download text link style */
    .download-text-link {{
        font-size: 11px;
        color: #888;
        text-decoration: none;
        display: block;
        margin-top: 8px;
        padding: 3px 0;
        transition: color 0.2s ease;
    }}
    .download-text-link:hover {{
        color: #333;
        text-decoration: underline;
    }}

    /* ZIP Download button wrapper for spacing */
    .zip-download-wrapper {{
        margin-top: 25px;
        margin-bottom: 20px;
    }}
    .zip-download-wrapper .stDownloadButton button {{
        font-weight: bold !important;
    }}
    </style>
""", unsafe_allow_html=True)

# --- Utility Functions ---
def shorten_filename(filename, name_max_len=20, front_chars=8, back_chars=7):
    """Shortens a filename for display, keeping parts of the name and the extension."""
    name_body, ext = os.path.splitext(filename)
    if len(name_body) > name_max_len:
        # Ensure front_chars and back_chars don't overlap or exceed name_max_len
        if front_chars + back_chars + 3 > name_max_len : # 3 for "..."
            # Basic heuristic to divide remaining length
            front_chars = max(1, (name_max_len - 3) // 2)
            back_chars = max(1, name_max_len - 3 - front_chars)
        return f"{name_body[:front_chars]}...{name_body[-back_chars:]}{ext}"
    return filename

# --- Color Extraction ---
def extract_palette(image: Image.Image, num_colors=6, quantize_method=Image.MEDIANCUT):
    """
    Extracts a color palette from the image.
    Uses a primary quantization method and falls back to FASTOCTREE if the primary fails.
    """
    img_rgb = image.convert("RGB") # Ensure image is in RGB mode
    try:
        # Attempt primary quantization method
        paletted_image = img_rgb.quantize(colors=num_colors, method=quantize_method)
        palette_data = paletted_image.getpalette() # Returns a flat list [r,g,b,r,g,b,...]

        if palette_data is None:
            st.warning(f"Palette extraction (method: {quantize_method}) returned None. Trying fallback or returning empty.")
            # Fallback directly in the except block might be cleaner if this is an error condition
            raise ValueError("Palette data is None")


        # Extract the first num_colors from the palette
        # Each color is 3 values (R, G, B)
        actual_colors_in_palette = len(palette_data) // 3
        colors_to_extract = min(num_colors, actual_colors_in_palette)
        
        extracted_colors = []
        for i in range(colors_to_extract):
            extracted_colors.append(tuple(palette_data[i*3 : i*3+3]))
        
        if not extracted_colors and num_colors > 0:
             st.caption(f"Could not extract {num_colors} distinct colors, got {len(extracted_colors)}. Image might have fewer colors.")

        return extracted_colors

    except (OSError, ValueError) as e:
        st.caption(f"Palette extraction with primary method failed: {e}. Trying FASTOCTREE.")
        try:
            # Fallback to FASTOCTREE
            paletted_image_fallback = img_rgb.quantize(colors=num_colors, method=Image.FASTOCTREE)
            palette_data_fallback = paletted_image_fallback.getpalette()

            if palette_data_fallback is None:
                st.warning("Palette extraction with FASTOCTREE fallback also returned None.")
                return []

            actual_colors_in_fallback_palette = len(palette_data_fallback) // 3
            colors_to_extract_fallback = min(num_colors, actual_colors_in_fallback_palette)

            fallback_colors = []
            for i in range(colors_to_extract_fallback):
                fallback_colors.append(tuple(palette_data_fallback[i*3 : i*3+3]))
            
            if not fallback_colors and num_colors > 0:
                st.caption(f"FASTOCTREE: Could not extract {num_colors} distinct colors, got {len(fallback_colors)}.")

            return fallback_colors
        except (OSError, ValueError) as e_fallback:
            st.error(f"Palette extraction failed with both primary and FASTOCTREE methods: {e_fallback}")
            st.exception(e_fallback) # Log the full exception for debugging
            return []
        except Exception as e_unknown_fallback: # Catch any other unexpected error during fallback
            st.error(f"An unexpected error occurred during FASTOCTREE palette extraction: {e_unknown_fallback}")
            st.exception(e_unknown_fallback)
            return []
    except Exception as e_unknown: # Catch any other unexpected error during primary method
        st.error(f"An unexpected error occurred during primary palette extraction: {e_unknown}")
        st.exception(e_unknown)
        return []


# --- Draw Layout Function ---
def draw_layout(image: Image.Image, colors: list, position: str, border_thickness_px: int,
                swatch_border_thickness: int, border_color: str, swatch_border_color: str,
                swatch_size_percent: int, remove_adjacent_border: bool):
    """
    Draws the image layout with color swatches.
    Swatch size is a percentage of the relevant image dimension.
    """
    img_w, img_h = image.size
    border = border_thickness_px

    # Determine actual swatch size in pixels
    if position in ['top', 'bottom']:
        # Swatch size is a percentage of image height for horizontal swatches
        actual_swatch_size_px = int(img_h * (swatch_size_percent / 100))
    else: # 'left', 'right'
        # Swatch size is a percentage of image width for vertical swatches
        actual_swatch_size_px = int(img_w * (swatch_size_percent / 100))
    actual_swatch_size_px = max(1, actual_swatch_size_px) # Ensure swatch is at least 1px

    # If no colors, just draw the image with its border
    if not colors:
        if border > 0:
            canvas = Image.new("RGB", (img_w + 2 * border, img_h + 2 * border), border_color)
            canvas.paste(image, (border, border))
            return canvas
        return image.copy() # Return a copy to avoid modifying original

    # Initialize canvas and drawing context
    # Variables for swatch dimensions and positioning
    swatch_width_per_color = 0
    swatch_height_per_color = 0
    extra_width_for_last_swatch = 0
    extra_height_for_last_swatch = 0
    current_swatch_x_start = 0
    current_swatch_y_start = 0
    swatch_fixed_coord_y = 0 # For top/bottom
    swatch_fixed_coord_x = 0 # For left/right

    if position == 'top':
        canvas_h = img_h + actual_swatch_size_px + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, actual_swatch_size_px + border)) # Image below swatches
        swatch_fixed_coord_y = border
        current_swatch_x_start = border
        total_swatch_area_width = img_w
        if colors:
            swatch_width_per_color = total_swatch_area_width // len(colors)
            extra_width_for_last_swatch = total_swatch_area_width % len(colors)
    elif position == 'bottom':
        canvas_h = img_h + actual_swatch_size_px + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, border)) # Image above swatches
        swatch_fixed_coord_y = border + img_h
        current_swatch_x_start = border
        total_swatch_area_width = img_w
        if colors:
            swatch_width_per_color = total_swatch_area_width // len(colors)
            extra_width_for_last_swatch = total_swatch_area_width % len(colors)
    elif position == 'left':
        canvas_w = img_w + actual_swatch_size_px + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (actual_swatch_size_px + border, border)) # Image to the right of swatches
        swatch_fixed_coord_x = border
        current_swatch_y_start = border
        total_swatch_area_height = img_h
        if colors:
            swatch_height_per_color = total_swatch_area_height // len(colors)
            extra_height_for_last_swatch = total_swatch_area_height % len(colors)
    elif position == 'right':
        canvas_w = img_w + actual_swatch_size_px + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, border)) # Image to the left of swatches
        swatch_fixed_coord_x = border + img_w
        current_swatch_y_start = border
        total_swatch_area_height = img_h
        if colors:
            swatch_height_per_color = total_swatch_area_height // len(colors)
            extra_height_for_last_swatch = total_swatch_area_height % len(colors)
    else: # Should not happen with current UI
        return image.copy()

    draw = ImageDraw.Draw(canvas)

    for i, color_tuple in enumerate(colors):
        # Determine current swatch dimensions (last swatch might be larger)
        current_w = swatch_width_per_color
        current_h = swatch_height_per_color

        x0, y0, x1, y1 = 0, 0, 0, 0

        if position in ['top', 'bottom']:
            if i == len(colors) - 1: current_w += extra_width_for_last_swatch
            x0 = current_swatch_x_start + i * swatch_width_per_color
            y0 = swatch_fixed_coord_y
            x1 = x0 + current_w
            y1 = y0 + actual_swatch_size_px
        else: # 'left', 'right'
            if i == len(colors) - 1: current_h += extra_height_for_last_swatch
            x0 = swatch_fixed_coord_x
            y0 = current_swatch_y_start + i * swatch_height_per_color
            x1 = x0 + actual_swatch_size_px
            y1 = y0 + current_h

        # Draw swatch fill
        draw.rectangle([x0, y0, x1, y1], fill=tuple(color_tuple))

        # Draw swatch border
        if swatch_border_thickness > 0:
            # Determine if swatch is adjacent to the main image border
            # (and thus one of its borders might be omitted if remove_adjacent_border is true)
            adj_to_top_img_border = (position == 'top' and y0 == border)
            adj_to_bottom_img_border = (position == 'bottom' and y1 == (canvas.height - border))
            adj_to_left_img_border = (position == 'left' and x0 == border)
            adj_to_right_img_border = (position == 'right' and x1 == (canvas.width - border))

            # Top line of swatch
            if not (remove_adjacent_border and adj_to_top_img_border and border_thickness_px == 0):
                 draw.line([(x0, y0), (x1 -1 , y0)], swatch_border_color, swatch_border_thickness)
            # Bottom line of swatch
            if not (remove_adjacent_border and adj_to_bottom_img_border and border_thickness_px == 0):
                 draw.line([(x0, y1 -1), (x1 -1, y1-1)], swatch_border_color, swatch_border_thickness)
            # Left line of swatch
            if not (remove_adjacent_border and adj_to_left_img_border and border_thickness_px == 0):
                 draw.line([(x0, y0), (x0, y1-1)], swatch_border_color, swatch_border_thickness)
            # Right line of swatch
            if not (remove_adjacent_border and adj_to_right_img_border and border_thickness_px == 0):
                 draw.line([(x1-1, y0), (x1-1, y1-1)], swatch_border_color, swatch_border_thickness)

            # Inner borders between swatches
            if i > 0: # Don't draw inner border for the first swatch
                if position in ['top', 'bottom']: # Vertical line separating horizontal swatches
                    draw.line([(x0, y0), (x0, y1-1)], swatch_border_color, swatch_border_thickness)
                else: # Horizontal line separating vertical swatches
                    draw.line([(x0, y0), (x1-1, y0)], swatch_border_color, swatch_border_thickness)
    return canvas

# --- Input Columns ---
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("1. Upload Images")
    allowed_types = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif"]
    uploaded_files = st.file_uploader("Choose images", accept_multiple_files=True, type=allowed_types, key="file_uploader")

    # Filter for valid extensions client-side (though uploader also does this)
    # This handles cases where type might be too permissive or user bypasses it.
    valid_files_after_upload = []
    if uploaded_files:
        valid_extensions_tuple = tuple(f".{ext.lower()}" for ext in allowed_types)
        for file_obj in uploaded_files:
            if not file_obj.name.lower().endswith(valid_extensions_tuple):
                st.warning(f"File `{file_obj.name}` has an unsupported extension. Skipped.")
            else:
                valid_files_after_upload.append(file_obj)
        uploaded_files = valid_files_after_upload # Reassign to the filtered list

    st.subheader("2. Download Options")
    resize_option = st.radio("Resize method", ["Original size", "Scale (%)"], index=0, key="resize_option")
    scale_percent = 100 # Default
    if resize_option == "Scale (%)":
        scale_percent = st.slider("Scale percent", 10, 200, 100, key="scale_percent")

    output_format_options = ["JPG", "PNG", "WEBP"]
    output_format = st.selectbox("Output format", output_format_options, index=0, key="output_format") # Default to JPG
    webp_lossless = False
    if output_format == "WEBP":
        webp_lossless = st.checkbox("Lossless WEBP", value=False, key="webp_lossless")

    # PIL format string and file extension
    format_map = {"JPG": ("JPEG", "jpg"), "PNG": ("PNG", "png"), "WEBP": ("WEBP", "webp")}
    img_format_pil, file_extension = format_map[output_format]

with col2:
    st.subheader("3. Layout Settings")
    positions = [] # List to store selected swatch positions
    st.write("Swatch position(s):")
    pos_cols = st.columns(4) # Use columns for compact toggle layout
    if pos_cols[0].toggle("Top", key="pos_top"): positions.append("top")
    if pos_cols[1].toggle("Bottom", value=True, key="pos_bottom"): positions.append("bottom") # Default bottom
    if pos_cols[2].toggle("Left", key="pos_left"): positions.append("left")
    if pos_cols[3].toggle("Right", key="pos_right"): positions.append("right")

    quant_method_label = st.selectbox("Palette method", ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"], index=0, key="quant_method")
    quant_method_map = {"MEDIANCUT": Image.MEDIANCUT, "MAXCOVERAGE": Image.MAXCOVERAGE, "FASTOCTREE": Image.FASTOCTREE}
    quantize_method_selected = quant_method_map[quant_method_label]

    num_colors = st.slider("Number of swatches", 2, 12, 6, key="num_colors")
    swatch_size_percent_val = st.slider("Swatch size (% of image dim.)", 5, 50, 20, key="swatch_size_percent")

with col3:
    st.subheader("4. Border Settings")
    border_thickness_percent = st.slider("Image border (% of width)", 0, 10, 0, key="border_thickness_percent")
    border_color = st.color_picker("Image border color", "#FFFFFF", key="border_color") # Default white
    swatch_border_thickness = st.slider("Swatch border (px)", 0, 10, 1, key="swatch_border_thickness")
    swatch_border_color = st.color_picker("Swatch border color", "#CCCCCC", key="swatch_border_color") # Default gray
    remove_adjacent_border = st.checkbox("Align swatches to image edge (no double border)", value=True, key="remove_adjacent_border")


# --- Process & Preview ---
if uploaded_files and positions:
    st.markdown("---")
    st.subheader("Previews")

    # Use a single placeholder for all preview HTML, updated once after loop
    preview_html_placeholder = preview_display_area_container.empty()
    individual_preview_html_parts = []
    processed_images_for_zip = 0
    zip_buffer = io.BytesIO() # In-memory buffer for the ZIP file

    # Using st.spinner as a context manager
    with st.spinner("Generating previews and preparing ZIP... Please wait."):
        # Open zip file once
        # compresslevel=0 means store, no compression. Good for speed if images are already compressed.
        # Use a higher level (e.g., 6 or 9) for better compression if needed.
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
            for uploaded_file_obj in uploaded_files:
                original_image_for_processing = None # To hold the successfully opened image
                try:
                    # Read file bytes
                    uploaded_file_bytes = uploaded_file_obj.getvalue()
                    # Attempt to open and verify the image
                    # image.verify() can be problematic, sometimes it's better to just try opening
                    # and catch exceptions. It also consumes the file pointer for some formats.
                    # Re-opening is necessary after verify.
                    temp_image = Image.open(io.BytesIO(uploaded_file_bytes))
                    temp_image.verify() # Check for basic integrity. Raises exception on error.
                    # If verify successful, re-open to use the image
                    original_image_for_processing = Image.open(io.BytesIO(uploaded_file_bytes))

                except UnidentifiedImageError:
                    st.warning(f"Cannot identify image format for `{uploaded_file_obj.name}`. It might be corrupted or unsupported. Skipped.")
                    continue
                except FileNotFoundError: # Should not happen with UploadedFile, but good practice
                    st.error(f"File `{uploaded_file_obj.name}` not found. Skipped.")
                    continue
                except Exception as e_open: # Catch other PIL opening errors or verify errors
                    st.error(f"Error opening or verifying `{uploaded_file_obj.name}`: {e_open}. Skipped.")
                    st.exception(e_open) # Provides full traceback in console/log for debugging
                    continue

                # Proceed if image was successfully opened
                if original_image_for_processing:
                    try:
                        w, h = original_image_for_processing.size
                        # Basic validation for image dimensions
                        if not (10 <= w <= 10000 and 10 <= h <= 10000): # Example limits
                            st.warning(f"`{uploaded_file_obj.name}` ({w}x{h}) has dimensions outside the typical range. Skipped.")
                            continue

                        # Ensure image is in a processable mode (e.g., RGB)
                        # 'L' (grayscale) can also be processed by quantize if converted to RGB
                        if original_image_for_processing.mode not in ("RGB", "RGBA", "L"):
                            image_to_process = original_image_for_processing.convert("RGB")
                        elif original_image_for_processing.mode == "RGBA": # Handle transparency if needed, or convert
                            image_to_process = original_image_for_processing.convert("RGB") # Simplest: convert and lose alpha
                        else:
                            image_to_process = original_image_for_processing.copy() # Work on a copy

                        # Extract palette
                        palette = extract_palette(image_to_process, num_colors, quantize_method_selected)
                        if not palette and num_colors > 0:
                             st.caption(f"No color palette extracted for `{uploaded_file_obj.name}`. Swatches will be empty or not drawn if this is unexpected.")


                    except Exception as e_palette:
                        st.error(f"Error during initial processing or palette extraction for `{uploaded_file_obj.name}`: {e_palette}. Skipped.")
                        st.exception(e_palette)
                        continue # Skip to next uploaded file

                    # Calculate border thickness in pixels (once per image)
                    border_px = int(image_to_process.width * (border_thickness_percent / 100))

                    # Generate layouts for each selected position
                    for pos_idx, pos in enumerate(positions):
                        try:
                            # Create a fresh copy for each layout to avoid interference
                            current_image_for_layout = image_to_process.copy()

                            result_img = draw_layout(current_image_for_layout, palette, pos, border_px,
                                                     swatch_border_thickness, border_color, swatch_border_color,
                                                     swatch_size_percent_val, remove_adjacent_border)

                            # Resize if needed
                            if resize_option == "Scale (%)" and scale_percent != 100:
                                new_w = int(result_img.width * scale_percent / 100)
                                new_h = int(result_img.height * scale_percent / 100)
                                if new_w > 0 and new_h > 0:
                                    # Using LANCZOS for high-quality downsampling
                                    result_img = result_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                                else:
                                    st.warning(f"Skipping resize for `{uploaded_file_obj.name}` (pos: {pos}) due to invalid new dimensions ({new_w}x{new_h}).")


                            # Prepare image for download and ZIP
                            img_byte_arr_download = io.BytesIO()
                            base_name, _ = os.path.splitext(uploaded_file_obj.name)
                            # Sanitize base_name for file systems
                            safe_base_name = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in base_name).strip()
                            name_for_file = f"{safe_base_name}_{pos}.{file_extension}"

                            save_params = {}
                            if img_format_pil == "JPEG": save_params['quality'] = 95 # Good quality for JPEG
                            elif img_format_pil == "WEBP":
                                save_params['quality'] = 85 # Default for lossy WEBP
                                if webp_lossless:
                                    save_params.update({'lossless': True, 'quality': 100}) # Max quality for lossless

                            result_img.save(img_byte_arr_download, format=img_format_pil, **save_params)
                            img_bytes_for_download = img_byte_arr_download.getvalue()

                            # Add to ZIP
                            zipf.writestr(name_for_file, img_bytes_for_download)
                            processed_images_for_zip += 1

                            # Prepare for individual download link in preview
                            img_base64_for_download = base64.b64encode(img_bytes_for_download).decode("utf-8")
                            mime_type_for_download = f"image/{img_format_pil.lower()}" # e.g., image/jpeg
                            data_uri_for_download = f"data:{mime_type_for_download};base64,{img_base64_for_download}"

                            # Generate thumbnail for preview display (use PNG for broad compatibility in data URI)
                            preview_img_for_display = result_img.copy()
                            preview_img_for_display.thumbnail((180, 180)) # Max width/height for thumbnail
                            with io.BytesIO() as buffer_display:
                                preview_img_for_display.save(buffer_display, format="PNG") # PNG for preview
                                img_base64_thumb = base64.b64encode(buffer_display.getvalue()).decode("utf-8")

                            display_name = shorten_filename(name_for_file, name_max_len=22, front_chars=10, back_chars=7)

                            single_item_html = f"""
                            <div class='preview-item'>
                                <div>
                                    <img src='data:image/png;base64,{img_base64_thumb}' alt='{name_for_file} Preview'>
                                    <div class='preview-item-name' title='{name_for_file}'>{display_name}</div>
                                </div>
                                <a href='{data_uri_for_download}' download='{name_for_file}' class='download-text-link' title='Download {name_for_file}'>Download Image</a>
                            </div>"""
                            individual_preview_html_parts.append(single_item_html)

                        except Exception as e_layout:
                            st.error(f"Error during layout or saving for `{uploaded_file_obj.name}` (position: {pos}): {e_layout}")
                            st.exception(e_layout) # Log full exception
                            # Continue to next position or file

            # After processing all files and positions, update the preview area once
            if individual_preview_html_parts:
                full_html_content = "<div id='preview-zone'>" + "\n".join(individual_preview_html_parts) + "</div>"
                preview_html_placeholder.markdown(full_html_content, unsafe_allow_html=True)
            elif uploaded_files and positions: # Files were uploaded, positions selected, but nothing processed
                 preview_html_placeholder.info("No previews generated. Check for error messages above.")


        # End of st.spinner context
        zip_buffer.seek(0) # Rewind buffer to the beginning for reading by download_button

    # --- Download Button ---
    with download_buttons_container: # Use the dedicated container
        st.markdown("<div class='zip-download-wrapper'>", unsafe_allow_html=True)
        if processed_images_for_zip > 0:
            st.download_button(
                label=f"⬇️ Download All as ZIP ({processed_images_for_zip} image{'s' if processed_images_for_zip > 1 else ''}, {output_format.upper()})",
                data=zip_buffer,
                file_name=f"ColorSwatches_{output_format.lower()}.zip",
                mime="application/zip",
                use_container_width=True,
                key="download_zip_main"
            )
        elif uploaded_files and positions: # Files uploaded, positions selected, but nothing made it to ZIP
            st.warning("No images were successfully processed for the ZIP download. Check error messages above.")
        st.markdown("</div>", unsafe_allow_html=True)

# --- Conditional Info Messages ---
elif uploaded_files and not positions:
    st.info("👉 Select at least one swatch position (Top, Bottom, Left, Right) to generate previews.")
    preview_display_area_container.empty() # Clear previous previews if any
    download_buttons_container.empty() # Clear download button
elif not uploaded_files:
    st.info("👋 Welcome! Upload images using the panel on the left to get started.")
    preview_display_area_container.empty()
    download_buttons_container.empty()

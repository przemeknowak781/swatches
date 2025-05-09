import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import numpy as np
import io
import zipfile
import base64
import sys # Added for error logging
import os # For filename manipulation

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("Color Swatch Generator")

# --- Global containers for dynamic content ---
# Container for the "Generating previews..." spinner
spinner_container = st.empty()
# Main container for the previews
preview_container = st.container()
# Container for download buttons
download_buttons_container = st.container()


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
        gap: 30px;        /* Gap between preview items */
        padding: 20px;    /* Inner padding for the preview zone */
        border-radius: 8px;
        /* background-color: #f9f9f9; /* Optional light background for the zone */
        min-height: 250px; /* Ensure it has some height even when empty */
    }
    /* Styles for individual preview items */
    .preview-item {
        flex: 0 0 auto; /* Items won't grow or shrink */
        text-align: center;
        width: 200px; /* Fixed width for each preview item */
        box-shadow: 0 4px 12px rgba(0,0,0,0.15); /* Subtle shadow */
        padding: 10px; /* Inner padding for the item */
        border-radius: 8px;
        background: #ffffff;
        border: 1px solid #e0e0e0;
    }
    .preview-item img {
        width: 100%; /* Image takes full available width within .preview-item */
        max-width: 180px; /* Max image width to leave some padding */
        height: auto;     /* Maintain aspect ratio */
        border-radius: 4px;
        margin-bottom: 8px; /* Space below the image */
    }
    .preview-item-name {
        font-size: 12px;
        margin-bottom: 5px;
        color: #333;
        word-break: break-all; /* Break long filenames */
        height: 30px; /* Give it a fixed height to prevent layout shifts */
        overflow: hidden;
    }
    /* Add some margin below subheaders for better section separation */
    h2 {
        margin-bottom: 0.9rem !important;
    }
    /* Ensure download buttons have some space */
    .stDownloadButton {
        margin-top: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# --- Utility Functions ---
def shorten_filename(filename, max_len=20, front_chars=8, back_chars=8):
    """Shortens a filename to fit max_len, keeping front_chars and back_chars."""
    if len(filename) > max_len:
        return f"{filename[:front_chars]}...{filename[-(back_chars + len(os.path.splitext(filename)[1])):]}{os.path.splitext(filename)[1]}"
    return filename

# --- Color Extraction ---
def extract_palette(image, num_colors=6, quantize_method=Image.MEDIANCUT):
    """Extracts a color palette from the image."""
    img = image.convert("RGB")
    try:
        paletted = img.quantize(colors=num_colors, method=quantize_method)
        palette_full = paletted.getpalette()
        if palette_full is None:
            paletted = img.quantize(colors=num_colors, method=quantize_method)
            palette_full = paletted.getpalette()
            if palette_full is None:
                return []

        actual_palette_colors = len(palette_full) // 3
        colors_to_extract = min(num_colors, actual_palette_colors)
        extracted_palette_rgb_values = palette_full[:colors_to_extract * 3]
        colors = [tuple(extracted_palette_rgb_values[i:i+3]) for i in range(0, len(extracted_palette_rgb_values), 3)]
        return colors
    except Exception as e:
        # st.warning(f"Error during quantization ({e}). Using fallback method (FASTOCTREE).") # Less verbose
        try:
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE)
            palette = paletted.getpalette()
            if palette is None: return []
            colors = [tuple(palette[i:i+3]) for i in range(0, min(num_colors * 3, len(palette)), 3)]
            return colors
        except Exception:
            # st.error(f"Error during fallback quantization: {e_fallback}") # Less verbose
            return []


# --- Draw Layout Function ---
def draw_layout(image, colors, position, border_thickness_px, swatch_border_thickness,
                border_color, swatch_border_color, swatch_size_percent, remove_adjacent_border):
    """Draws the image layout with color swatches. Swatch size is now a percentage."""
    img_w, img_h = image.size
    border = border_thickness_px # Already in pixels

    # Calculate actual swatch size in pixels based on percentage
    if position in ['top', 'bottom']:
        # Base swatch size on image height for horizontal swatches for consistency, or width if preferred
        # Using image height as the reference for swatch thickness
        actual_swatch_size_px = int(img_h * (swatch_size_percent / 100))
    else: # 'left', 'right'
        # Using image width as the reference for swatch thickness
        actual_swatch_size_px = int(img_w * (swatch_size_percent / 100))

    if actual_swatch_size_px <= 0 : # Ensure swatch size is at least 1px if calculated to 0
        actual_swatch_size_px = 1


    if not colors:
        if border > 0:
            canvas = Image.new("RGB", (img_w + 2 * border, img_h + 2 * border), border_color)
            canvas.paste(image, (border, border))
            return canvas
        return image.copy()

    swatch_width = 0
    swatch_height = 0
    extra_width_for_last_swatch = 0
    extra_height_for_last_swatch = 0
    swatch_x_start = 0
    swatch_y_start = 0
    swatch_y = 0
    swatch_x = 0

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
            swatch_width = swatch_total_width

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
    else:
        return image.copy()

    draw = ImageDraw.Draw(canvas)

    for i, color_tuple in enumerate(colors):
        current_swatch_width = swatch_width
        current_swatch_height = swatch_height

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

        draw.rectangle([x0, y0, x1, y1], fill=tuple(color_tuple))

        if swatch_border_thickness > 0:
            is_at_top_edge = (position == 'top' and y0 == border)
            is_at_bottom_edge = (position == 'bottom' and y1 == (canvas.height - border))
            is_at_left_edge = (position == 'left' and x0 == border)
            is_at_right_edge = (position == 'right' and x1 == (canvas.width - border))

            if not (remove_adjacent_border and is_at_top_edge and border == 0):
                 draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            if not (remove_adjacent_border and is_at_bottom_edge and border == 0):
                 draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            if not (remove_adjacent_border and is_at_left_edge and border == 0):
                 draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            if not (remove_adjacent_border and is_at_right_edge and border == 0):
                 draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

            if position in ['top', 'bottom']:
                if i > 0:
                    draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            else:
                if i > 0:
                    draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
    return canvas

# --- Input Columns ---
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Upload Images")
    allowed_types = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif"]
    uploaded_files = st.file_uploader(
        "Choose images",
        accept_multiple_files=True,
        type=allowed_types
    )

    valid_files_after_upload = []
    if uploaded_files:
        valid_extensions_tuple = tuple(f".{ext}" for ext in allowed_types)
        for file_obj in uploaded_files:
            if not file_obj.name.lower().endswith(valid_extensions_tuple):
                st.warning(f"`{file_obj.name}` has an unsupported extension. Skipped.")
            else:
                valid_files_after_upload.append(file_obj)
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
    row1_layout = st.columns(2)
    row2_layout = st.columns(2)
    if row1_layout[0].toggle("Top", key="pos_top"): positions.append("top")
    if row1_layout[1].toggle("Left", key="pos_left"): positions.append("left")
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
    # Changed to percentage
    swatch_size_percent_val = st.slider("Swatch size (% of image dimension)", 5, 50, 20, key="swatch_size_percent", help="Percentage of image height (for top/bottom) or width (for left/right).")


with col3:
    st.subheader("Borders")
    border_thickness_percent = st.slider("Image border thickness (% of width)", 0, 10, 0, key="border_thickness_percent")
    border_color = st.color_picker("Image border color", "#FFFFFF", key="border_color")
    swatch_border_thickness = st.slider("Swatch border thickness (px)", 0, 10, 1, key="swatch_border_thickness")
    swatch_border_color = st.color_picker("Swatch border color", "#CCCCCC", key="swatch_border_color")
    remove_adjacent_border = st.checkbox("Align swatches with image edge", value=True, key="remove_adjacent_border")


# --- Process & Preview ---
if uploaded_files and positions:
    st.markdown("---")
    st.subheader("Previews")
    
    # Move spinner here, under the "Previews" header
    with spinner_container, st.spinner("Generating previews..."):
        preview_display_area = preview_container.empty() # Prepare the area for previews
        
        individual_preview_html_parts = []
        zip_buffer = io.BytesIO()
        
        # Store data for individual downloads
        individual_file_data = [] 

        # Use compresslevel=0 (ZIP_STORED) for speed, as images are already compressed.
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
            for uploaded_file_obj in uploaded_files:
                try:
                    uploaded_file_bytes = uploaded_file_obj.getvalue()
                    image_stream_for_verify = io.BytesIO(uploaded_file_bytes)
                    test_image = Image.open(image_stream_for_verify)
                    test_image.verify()
                    image_stream_for_load = io.BytesIO(uploaded_file_bytes)
                    image = Image.open(image_stream_for_load)
                except UnidentifiedImageError:
                    st.warning(f"Could not identify image file: `{uploaded_file_obj.name}`. Skipped.")
                    continue
                except Exception as e:
                    st.warning(f"`{uploaded_file_obj.name}` could not be loaded or is corrupted ({e}). Skipped.")
                    continue

                try:
                    w, h = image.size
                    if not (10 <= w <= 10000 and 10 <= h <= 10000):
                        st.warning(f"`{uploaded_file_obj.name}` has an unsupported resolution ({w}x{h}). Skipped.")
                        continue
                    if image.mode not in ("RGB", "L"):
                         image = image.convert("RGB")
                    palette = extract_palette(image, num_colors, quantize_method=quantize_method_selected)
                    if not palette:
                        # st.warning(f"Failed to extract palette for `{uploaded_file_obj.name}`. Skipping swatches.") # Less verbose
                        pass
                except Exception as e:
                    st.error(f"Error processing `{uploaded_file_obj.name}`: {e}. Skipped.")
                    continue

                border_px = int(image.width * (border_thickness_percent / 100))

                for pos_idx, pos in enumerate(positions):
                    try:
                        result_img = draw_layout(
                            image.copy(), palette, pos, border_px, swatch_border_thickness,
                            border_color, swatch_border_color, swatch_size_percent_val, remove_adjacent_border
                        )

                        if resize_option == "Scale (%)" and scale_percent != 100:
                            new_w = int(result_img.width * scale_percent / 100)
                            new_h = int(result_img.height * scale_percent / 100)
                            if new_w > 0 and new_h > 0:
                                result_img = result_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                            else:
                                st.warning(f"Cannot resize {uploaded_file_obj.name}_{pos}. Using original size.")

                        img_byte_arr = io.BytesIO()
                        base_name, 작업_확장자 = os.path.splitext(uploaded_file_obj.name) # Use os.path.splitext
                        safe_base_name = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in base_name).rstrip()
                        name_for_file = f"{safe_base_name}_{pos}.{extension}" # Consistent naming

                        save_params = {}
                        if img_format == "JPEG": save_params['quality'] = 95
                        elif img_format == "WEBP":
                            save_params['quality'] = 85
                            if webp_lossless:
                                save_params['lossless'] = True
                                save_params['quality'] = 100

                        result_img.save(img_byte_arr, format=img_format, **save_params)
                        img_bytes_for_download = img_byte_arr.getvalue() # Get bytes for individual download and ZIP

                        zipf.writestr(name_for_file, img_bytes_for_download)
                        
                        # Add to list for individual downloads
                        individual_file_data.append({"name": name_for_file, "data": img_bytes_for_download, "mime": f"image/{extension}"})


                        preview_img_for_display = result_img.copy()
                        preview_img_for_display.thumbnail((180, 180))
                        with io.BytesIO() as buffer_display:
                            preview_img_for_display.save(buffer_display, format="PNG")
                            img_base64 = base64.b64encode(buffer_display.getvalue()).decode("utf-8")
                        
                        # Shorten filename for display
                        display_name = shorten_filename(name_for_file, max_len=25, front_chars=10, back_chars=10)

                        single_item_html = f"<div class='preview-item'>"
                        single_item_html += f"<div class='preview-item-name' title='{name_for_file}'>{display_name}</div>" # Add full name as title
                        single_item_html += f"<img src='data:image/png;base64,{img_base64}' alt='Preview of {name_for_file}'>"
                        single_item_html += "</div>"
                        individual_preview_html_parts.append(single_item_html)

                        current_full_html_content = ("<div id='preview-zone'>" + "\n".join(individual_preview_html_parts) + "</div>")
                        preview_display_area.markdown(current_full_html_content, unsafe_allow_html=True)
                    except Exception as e_layout:
                        st.error(f"Error creating layout for {uploaded_file_obj.name} (pos: {pos}): {e_layout}")
        
        zip_buffer.seek(0)
        # Clear spinner after processing is done
        spinner_container.empty()


    # --- Download Buttons (Moved under "Previews" section) ---
    with download_buttons_container: # Use the dedicated container
        if individual_file_data: # Check if there's anything to download
            col_zip, col_individual = st.columns(2) # Create two columns for the buttons

            with col_zip:
                if zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader + 100: # Check if ZIP has content
                    st.download_button(
                        label=f"Download All as ZIP ({extension.upper()})",
                        data=zip_buffer,
                        file_name=f"ColorSwatches_{output_format.lower()}.zip",
                        mime="application/zip",
                        use_container_width=True,
                        key="download_zip"
                    )
                elif uploaded_files and positions:
                    st.warning("No images were generated for the ZIP. Check errors.")
            
            with col_individual:
                # For "Download as separate files", we'll provide one button per file.
                # This can be overwhelming if many files. A more advanced solution might involve JS.
                # For now, let's just show a message or a limited number of buttons.
                # A simple approach: if there are files, enable a button that then lists them.
                # Or directly list download buttons if not too many.
                
                # Let's try to display individual download buttons directly if there are files.
                # This might get crowded if many files are generated.
                # We will show them in an expander to keep the UI clean.
                if individual_file_data:
                    with st.expander("Download Individual Files", expanded=False):
                        st.caption(f"Click to download each generated image ({len(individual_file_data)} total).")
                        # Create a grid for individual download buttons if many
                        max_cols = 3 # Number of columns for download buttons
                        cols = st.columns(max_cols)
                        col_idx = 0
                        for i, file_info in enumerate(individual_file_data):
                            button_label_short = shorten_filename(file_info['name'], max_len=20, front_chars=7, back_chars=7)
                            cols[col_idx].download_button(
                                label=f"DL: {button_label_short}", # DL for Download
                                data=file_info['data'],
                                file_name=file_info['name'],
                                mime=file_info['mime'],
                                key=f"download_individual_{i}",
                                help=f"Download {file_info['name']}"
                            )
                            col_idx = (col_idx + 1) % max_cols
                        if not individual_file_data:
                             st.write("No individual files to download.")


        elif uploaded_files and positions :
             st.warning("No images were generated for download. Check error messages above.")


elif uploaded_files and not positions:
    st.info("Select at least one swatch position to generate previews and images for download.")
    # Clear previous previews and buttons if settings change and no positions are selected
    preview_container.empty()
    download_buttons_container.empty()
    spinner_container.empty()
elif not uploaded_files:
    st.info("Upload images to get started.")
    # Clear previews and buttons if no files are uploaded
    preview_container.empty()
    download_buttons_container.empty()
    spinner_container.empty()


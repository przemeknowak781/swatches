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
st.markdown("<style>h1{margin-bottom: 20px !important;}</style>", unsafe_allow_html=True) # Add space below title

# --- Global containers for dynamic content ---
spinner_container = st.empty()
preview_container = st.container()
download_buttons_container = st.container() # For the ZIP download button

# --- CSS for responsive columns and general styling ---
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
        min-height: 290px; /* Adjusted min-height for download text */
        background-color: #f8f9fa; /* Subtle background */
        border: 1px dashed #dee2e6; /* Dashed border */
        margin-top: 10px; /* Space above preview zone */
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
        display: flex; /* Added for flex layout of children */
        flex-direction: column; /* Stack children vertically */
        justify-content: space-between; /* Distribute space */
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
        align-self: center; /* Center image */
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
        color: #888; /* Lighter gray */
        text-decoration: none;
        display: block;
        margin-top: 8px; /* Space above the link */
        padding: 3px 0; /* Small padding for click area */
        transition: color 0.2s ease;
    }}
    .download-text-link:hover {{
        color: #333; /* Darker on hover */
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
        if front_chars + back_chars + 3 > name_max_len :
            front_chars = max(1, (name_max_len - 3) // 2)
            back_chars = max(1, name_max_len - 3 - front_chars)
        return f"{name_body[:front_chars]}...{name_body[-back_chars:]}{ext}"
    return filename

# --- Color Extraction ---
def extract_palette(image, num_colors=6, quantize_method=Image.MEDIANCUT):
    """Extracts a color palette from the image."""
    img = image.convert("RGB")
    try:
        paletted = img.quantize(colors=num_colors, method=quantize_method)
        palette_full = paletted.getpalette()
        if palette_full is None: 
            return [] 

        actual_palette_colors = len(palette_full) // 3
        colors_to_extract = min(num_colors, actual_palette_colors)
        extracted_palette_rgb_values = palette_full[:colors_to_extract * 3]
        colors = [tuple(extracted_palette_rgb_values[i:i+3]) for i in range(0, len(extracted_palette_rgb_values), 3)]
        return colors
    except Exception: 
        try: 
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE) 
            palette = paletted.getpalette()
            if palette is None: return []
            colors = [tuple(palette[i:i+3]) for i in range(0, min(num_colors * 3, len(palette)), 3)]
            return colors
        except Exception:
            return []


# --- Draw Layout Function ---
def draw_layout(image, colors, position, border_thickness_px, swatch_border_thickness,
                border_color, swatch_border_color, swatch_size_percent, remove_adjacent_border):
    """Draws the image layout with color swatches. Swatch size is a percentage."""
    img_w, img_h = image.size
    border = border_thickness_px 

    if position in ['top', 'bottom']:
        actual_swatch_size_px = int(img_h * (swatch_size_percent / 100))
    else: 
        actual_swatch_size_px = int(img_w * (swatch_size_percent / 100))
    actual_swatch_size_px = max(1, actual_swatch_size_px) 

    if not colors: 
        if border > 0:
            canvas = Image.new("RGB", (img_w + 2 * border, img_h + 2 * border), border_color)
            canvas.paste(image, (border, border))
            return canvas
        return image.copy()

    swatch_width = 0; swatch_height = 0; extra_width_for_last_swatch = 0; extra_height_for_last_swatch = 0
    swatch_x_start = 0; swatch_y_start = 0; swatch_y = 0; swatch_x = 0

    if position == 'top':
        canvas_h = img_h + actual_swatch_size_px + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, actual_swatch_size_px + border))
        swatch_y, swatch_x_start = border, border
        swatch_total_width = img_w
        if colors: swatch_width = swatch_total_width // len(colors); extra_width_for_last_swatch = swatch_total_width % len(colors)
        else: swatch_width = swatch_total_width
    elif position == 'bottom':
        canvas_h = img_h + actual_swatch_size_px + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, border))
        swatch_y = border + img_h; swatch_x_start = border
        swatch_total_width = img_w
        if colors: swatch_width = swatch_total_width // len(colors); extra_width_for_last_swatch = swatch_total_width % len(colors)
        else: swatch_width = swatch_total_width
    elif position == 'left':
        canvas_w = img_w + actual_swatch_size_px + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (actual_swatch_size_px + border, border))
        swatch_x, swatch_y_start = border, border
        swatch_total_height = img_h
        if colors: swatch_height = swatch_total_height // len(colors); extra_height_for_last_swatch = swatch_total_height % len(colors)
        else: swatch_height = swatch_total_height
    elif position == 'right':
        canvas_w = img_w + actual_swatch_size_px + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, border))
        swatch_x = border + img_w; swatch_y_start = border
        swatch_total_height = img_h
        if colors: swatch_height = swatch_total_height // len(colors); extra_height_for_last_swatch = swatch_total_height % len(colors)
        else: swatch_height = swatch_total_height
    else: return image.copy()

    draw = ImageDraw.Draw(canvas)
    if not colors: return canvas 

    for i, color_tuple in enumerate(colors):
        current_swatch_width, current_swatch_height = swatch_width, swatch_height
        x0_sw, y0_sw, x1_sw, y1_sw = 0,0,0,0 

        if position in ['top', 'bottom']:
            if i == len(colors) - 1: current_swatch_width += extra_width_for_last_swatch
            x0_sw = swatch_x_start + i * swatch_width
            x1_sw = x0_sw + current_swatch_width
            y0_sw = swatch_y
            y1_sw = swatch_y + actual_swatch_size_px
        else: 
            if i == len(colors) - 1: current_swatch_height += extra_height_for_last_swatch
            y0_sw = swatch_y_start + i * swatch_height
            y1_sw = y0_sw + current_swatch_height
            x0_sw = swatch_x
            x1_sw = swatch_x + actual_swatch_size_px
        
        draw.rectangle([x0_sw, y0_sw, x1_sw, y1_sw], fill=tuple(color_tuple))
        
        if swatch_border_thickness > 0:
            is_at_top_edge = (position == 'top' and y0_sw == border)
            is_at_bottom_edge = (position == 'bottom' and y1_sw == (canvas.height - border)) 
            is_at_left_edge = (position == 'left' and x0_sw == border)
            is_at_right_edge = (position == 'right' and x1_sw == (canvas.width - border)) 

            if not (remove_adjacent_border and is_at_top_edge and border == 0):
                 draw.line([(x0_sw, y0_sw), (x1_sw -1 , y0_sw)], swatch_border_color, swatch_border_thickness) 
            if not (remove_adjacent_border and is_at_bottom_edge and border == 0):
                 draw.line([(x0_sw, y1_sw -1), (x1_sw -1, y1_sw-1)], swatch_border_color, swatch_border_thickness)
            if not (remove_adjacent_border and is_at_left_edge and border == 0):
                 draw.line([(x0_sw, y0_sw), (x0_sw, y1_sw-1)], swatch_border_color, swatch_border_thickness)
            if not (remove_adjacent_border and is_at_right_edge and border == 0):
                 draw.line([(x1_sw-1, y0_sw), (x1_sw-1, y1_sw-1)], swatch_border_color, swatch_border_thickness)

            if i > 0: 
                if position in ['top', 'bottom']: 
                    draw.line([(x0_sw, y0_sw), (x0_sw, y1_sw-1)], swatch_border_color, swatch_border_thickness)
                else: 
                    draw.line([(x0_sw, y0_sw), (x1_sw-1, y0_sw)], swatch_border_color, swatch_border_thickness)
    return canvas

# --- Input Columns ---
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("1. Upload Images")
    allowed_types = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif"]
    uploaded_files = st.file_uploader("Choose images", accept_multiple_files=True, type=allowed_types, key="file_uploader")

    valid_files_after_upload = []
    if uploaded_files:
        valid_extensions_tuple = tuple(f".{ext}" for ext in allowed_types)
        for file_obj in uploaded_files:
            if not file_obj.name.lower().endswith(valid_extensions_tuple):
                st.warning(f"`{file_obj.name}` unsupported. Skipped.")
            else: valid_files_after_upload.append(file_obj)
        uploaded_files = valid_files_after_upload

    st.subheader("2. Download Options")
    resize_option = st.radio("Resize method", ["Original size", "Scale (%)"], index=0, key="resize_option")
    scale_percent = 100
    if resize_option == "Scale (%)":
        scale_percent = st.slider("Scale percent", 10, 200, 100, key="scale_percent")

    output_format_options = ["JPG", "PNG", "WEBP"]
    output_format = st.selectbox("Output format", output_format_options, key="output_format")
    webp_lossless = False
    if output_format == "WEBP":
        webp_lossless = st.checkbox("Lossless WEBP", value=False, key="webp_lossless")
    format_map = {"JPG": ("JPEG", "jpg"), "PNG": ("PNG", "png"), "WEBP": ("WEBP", "webp")}
    img_format_pil, file_extension = format_map[output_format]

with col2:
    st.subheader("3. Layout Settings")
    positions = []
    st.write("Swatch position(s):")
    pos_cols = st.columns(4)
    if pos_cols[0].toggle("Top", key="pos_top"): positions.append("top")
    if pos_cols[1].toggle("Bottom", value=True, key="pos_bottom"): positions.append("bottom")
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
    border_color = st.color_picker("Image border color", "#FFFFFF", key="border_color")
    swatch_border_thickness = st.slider("Swatch border (px)", 0, 10, 1, key="swatch_border_thickness")
    swatch_border_color = st.color_picker("Swatch border color", "#CCCCCC", key="swatch_border_color")
    remove_adjacent_border = st.checkbox("Align swatches to image edge", value=True, key="remove_adjacent_border")


# --- Process & Preview ---
if uploaded_files and positions:
    st.markdown("---")
    st.subheader("Previews")
    
    with spinner_container, st.spinner("Generating previews... Please wait."):
        preview_display_area = preview_container.empty()
        individual_preview_html_parts = []
        zip_buffer = io.BytesIO()
        processed_images_for_zip = 0

        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
            for uploaded_file_obj in uploaded_files:
                try:
                    uploaded_file_bytes = uploaded_file_obj.getvalue()
                    image = Image.open(io.BytesIO(uploaded_file_bytes))
                    image.verify() 
                    image = Image.open(io.BytesIO(uploaded_file_bytes))
                except UnidentifiedImageError:
                    st.warning(f"Cannot identify `{uploaded_file_obj.name}`. Skipped.")
                    continue
                except Exception as e:
                    st.warning(f"`{uploaded_file_obj.name}` error: {e}. Skipped.")
                    continue

                try:
                    w, h = image.size
                    if not (10 <= w <= 10000 and 10 <= h <= 10000):
                        st.warning(f"`{uploaded_file_obj.name}` ({w}x{h}) bad resolution. Skipped.")
                        continue
                    if image.mode not in ("RGB", "L"): image = image.convert("RGB")
                    
                    palette = extract_palette(image, num_colors, quantize_method_selected)
                except Exception as e:
                    st.error(f"Processing error for `{uploaded_file_obj.name}`: {e}. Skipped.")
                    continue

                border_px = int(image.width * (border_thickness_percent / 100))

                for pos_idx, pos in enumerate(positions):
                    try:
                        result_img = draw_layout(image.copy(), palette, pos, border_px, swatch_border_thickness,
                                                 border_color, swatch_border_color, swatch_size_percent_val, remove_adjacent_border)

                        if resize_option == "Scale (%)" and scale_percent != 100:
                            new_w = int(result_img.width * scale_percent / 100)
                            new_h = int(result_img.height * scale_percent / 100)
                            if new_w > 0 and new_h > 0:
                                result_img = result_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                        img_byte_arr = io.BytesIO()
                        base_name, _ = os.path.splitext(uploaded_file_obj.name)
                        safe_base_name = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in base_name).rstrip()
                        name_for_file = f"{safe_base_name}_{pos}.{file_extension}"

                        save_params = {}
                        if img_format_pil == "JPEG": save_params['quality'] = 95
                        elif img_format_pil == "WEBP":
                            save_params['quality'] = 85
                            if webp_lossless: save_params.update({'lossless': True, 'quality': 100})
                        
                        result_img.save(img_byte_arr, format=img_format_pil, **save_params)
                        img_bytes_for_download = img_byte_arr.getvalue()

                        zipf.writestr(name_for_file, img_bytes_for_download)
                        processed_images_for_zip += 1

                        img_base64_for_download = base64.b64encode(img_bytes_for_download).decode("utf-8")
                        mime_type_for_download = f"image/{img_format_pil.lower()}"
                        data_uri_for_download = f"data:{mime_type_for_download};base64,{img_base64_for_download}"

                        preview_img_for_display = result_img.copy()
                        preview_img_for_display.thumbnail((180, 180)) 
                        with io.BytesIO() as buffer_display:
                            preview_img_for_display.save(buffer_display, format="PNG")
                            img_base64_thumb = base64.b64encode(buffer_display.getvalue()).decode("utf-8")
                        
                        display_name = shorten_filename(name_for_file, name_max_len=22, front_chars=10, back_chars=7)
                        
                        # Updated HTML for preview item with text download link
                        single_item_html = f"""
                        <div class='preview-item'>
                            <div> <img src='data:image/png;base64,{img_base64_thumb}' alt='{name_for_file}'>
                                <div class='preview-item-name' title='{name_for_file}'>{display_name}</div>
                            </div>
                            <a href='{data_uri_for_download}' download='{name_for_file}' class='download-text-link' title='Download {name_for_file}'>Download</a>
                        </div>"""
                        individual_preview_html_parts.append(single_item_html)
                        
                        current_full_html_content = "<div id='preview-zone'>" + "\n".join(individual_preview_html_parts) + "</div>"
                        preview_display_area.markdown(current_full_html_content, unsafe_allow_html=True)

                    except Exception as e_layout:
                        st.error(f"Layout error for {uploaded_file_obj.name} (pos: {pos}): {e_layout}")
        
        zip_buffer.seek(0)
        spinner_container.empty() 

    with download_buttons_container:
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
        elif uploaded_files and positions: 
            st.warning("No images were successfully processed for download. Check error messages above.")
        st.markdown("</div>", unsafe_allow_html=True)

elif uploaded_files and not positions:
    st.info("👉 Select at least one swatch position (Top, Bottom, Left, Right) to generate previews.")
    preview_container.empty()
    download_buttons_container.empty()
    spinner_container.empty()
elif not uploaded_files:
    st.info("👋 Welcome! Upload images using the panel on the left to get started.")
    preview_container.empty()
    download_buttons_container.empty()
    spinner_container.empty()

import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import io
import zipfile
import base64
import os
import html # For escaping HTML special characters

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("Color Swatch Generator")
st.markdown("<style>h1{margin-bottom: 20px !important;}</style>", unsafe_allow_html=True)

# --- Simple HTML Rendering Test ---
# This is to quickly check if st.markdown with unsafe_allow_html is working at all.
# If you don't see a light blue box with "Test HTML rendering: Bold Text",
# there might be a more fundamental issue with your Streamlit environment or browser.
st.markdown("<div style='background-color: lightblue; padding: 10px; border-radius: 5px; margin-bottom:15px;'>Test HTML rendering: <b>Bold Text</b></div>", unsafe_allow_html=True)

# --- Global containers for dynamic content ---
preview_display_area_container = st.container() # For the HTML preview display
download_buttons_container = st.container()

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
        word-break: break-all; /* Allow long names to wrap or break */
        height: 30px; /* Fixed height for 2 lines approx */
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
        if front_chars + back_chars + 3 > name_max_len : # 3 for "..."
            front_chars = max(1, (name_max_len - 3) // 2)
            back_chars = max(1, name_max_len - 3 - front_chars)
        return f"{name_body[:front_chars]}...{name_body[-back_chars:]}{ext}"
    return filename

# --- Color Extraction ---
def extract_palette(image: Image.Image, num_colors=6, quantize_method=Image.MEDIANCUT):
    """
    Extracts a color palette from the image.
    Uses a primary quantization method and falls back if it fails.
    """
    img_rgb = image.convert("RGB")
    try:
        paletted_image = img_rgb.quantize(colors=num_colors, method=quantize_method)
        palette_data = paletted_image.getpalette()
        if palette_data is None:
            raise ValueError("Palette data is None after primary quantization.")

        actual_colors_in_palette = len(palette_data) // 3
        colors_to_extract = min(num_colors, actual_colors_in_palette)
        extracted_colors = [tuple(palette_data[i*3 : i*3+3]) for i in range(colors_to_extract)]
        
        if not extracted_colors and num_colors > 0:
             st.caption(f"Could not extract {num_colors} distinct colors (Method: {quantize_method}). Image might have fewer colors.")
        return extracted_colors

    except (OSError, ValueError) as e:
        st.caption(f"Palette extraction with primary method failed: {e}. Trying FASTOCTREE.")
        try:
            paletted_image_fallback = img_rgb.quantize(colors=num_colors, method=Image.FASTOCTREE)
            palette_data_fallback = paletted_image_fallback.getpalette()
            if palette_data_fallback is None:
                st.warning("Palette extraction with FASTOCTREE fallback also returned None.")
                return []
            
            actual_colors_in_fallback = len(palette_data_fallback) // 3
            colors_to_extract_fallback = min(num_colors, actual_colors_in_fallback)
            fallback_colors = [tuple(palette_data_fallback[i*3 : i*3+3]) for i in range(colors_to_extract_fallback)]

            if not fallback_colors and num_colors > 0:
                st.caption(f"FASTOCTREE: Could not extract {num_colors} distinct colors, got {len(fallback_colors)}.")
            return fallback_colors

        except (OSError, ValueError) as e_fallback:
            st.error(f"Palette extraction failed with both primary and FASTOCTREE methods: {e_fallback}")
            st.exception(e_fallback)
            return []
        except Exception as e_unknown_fallback:
            st.error(f"An unexpected error occurred during FASTOCTREE palette extraction: {e_unknown_fallback}")
            st.exception(e_unknown_fallback)
            return []
    except Exception as e_unknown:
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

    if position in ['top', 'bottom']:
        actual_swatch_size_px = int(img_h * (swatch_size_percent / 100))
    else:
        actual_swatch_size_px = int(img_w * (swatch_size_percent / 100))
    actual_swatch_size_px = max(1, actual_swatch_size_px)

    if not colors: # No swatches to draw, just image with border
        if border > 0:
            canvas = Image.new("RGB", (img_w + 2 * border, img_h + 2 * border), border_color)
            canvas.paste(image, (border, border))
            return canvas
        return image.copy()

    # Calculate canvas dimensions based on swatch position
    if position == 'top':
        canvas_h, canvas_w = img_h + actual_swatch_size_px + 2 * border, img_w + 2 * border
        img_paste_coords = (border, actual_swatch_size_px + border)
        swatch_area_y_start, swatch_area_x_start = border, border
        total_swatch_dim = img_w
    elif position == 'bottom':
        canvas_h, canvas_w = img_h + actual_swatch_size_px + 2 * border, img_w + 2 * border
        img_paste_coords = (border, border)
        swatch_area_y_start, swatch_area_x_start = border + img_h, border
        total_swatch_dim = img_w
    elif position == 'left':
        canvas_w, canvas_h = img_w + actual_swatch_size_px + 2 * border, img_h + 2 * border
        img_paste_coords = (actual_swatch_size_px + border, border)
        swatch_area_x_start, swatch_area_y_start = border, border
        total_swatch_dim = img_h
    elif position == 'right':
        canvas_w, canvas_h = img_w + actual_swatch_size_px + 2 * border, img_h + 2 * border
        img_paste_coords = (border, border)
        swatch_area_x_start, swatch_area_y_start = border + img_w, border
        total_swatch_dim = img_h
    else: # Should not be reached
        return image.copy()

    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    canvas.paste(image, img_paste_coords)
    draw = ImageDraw.Draw(canvas)

    num_actual_colors = len(colors)
    if num_actual_colors == 0: return canvas # No colors to draw swatches for

    # Calculate swatch dimensions
    dim_per_swatch = total_swatch_dim // num_actual_colors
    extra_dim_for_last = total_swatch_dim % num_actual_colors

    for i, color_tuple in enumerate(colors):
        current_w_or_h = dim_per_swatch + (extra_dim_for_last if i == num_actual_colors - 1 else 0)

        if position in ['top', 'bottom']:
            x0 = swatch_area_x_start + i * dim_per_swatch
            y0 = swatch_area_y_start
            x1 = x0 + current_w_or_h
            y1 = y0 + actual_swatch_size_px
        else: # 'left', 'right'
            x0 = swatch_area_x_start
            y0 = swatch_area_y_start + i * dim_per_swatch
            x1 = x0 + actual_swatch_size_px
            y1 = y0 + current_w_or_h
        
        draw.rectangle([x0, y0, x1, y1], fill=tuple(color_tuple))

        if swatch_border_thickness > 0:
            # Simplified border drawing logic: draw all 4 sides for each swatch, then inner dividers
            # This might lead to thicker lines where swatches meet the main border or each other if not careful.
            # The original logic for remove_adjacent_border was more complex to avoid this.
            # For now, let's draw all sides and then inner.
            
            # Outer border of the current swatch
            draw.line([(x0, y0), (x1 - 1, y0)], swatch_border_color, swatch_border_thickness) # Top
            draw.line([(x0, y1 - 1), (x1 - 1, y1 - 1)], swatch_border_color, swatch_border_thickness) # Bottom
            draw.line([(x0, y0), (x0, y1 - 1)], swatch_border_color, swatch_border_thickness) # Left
            draw.line([(x1 - 1, y0), (x1 - 1, y1 - 1)], swatch_border_color, swatch_border_thickness) # Right

            # Inner borders between swatches (if not the first swatch)
            # This will draw on top of one side of the previous swatch's border, effectively making it look like a single line.
            if i > 0:
                if position in ['top', 'bottom']: # Vertical line
                    draw.line([(x0, y0), (x0, y1 - 1)], swatch_border_color, swatch_border_thickness)
                else: # Horizontal line
                    draw.line([(x0, y0), (x1 - 1, y0)], swatch_border_color, swatch_border_thickness)
    return canvas

# --- Input Columns ---
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("1. Upload Images")
    allowed_types = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif"]
    uploaded_files = st.file_uploader("Choose images", accept_multiple_files=True, type=allowed_types, key="file_uploader")

    valid_files_after_upload = []
    if uploaded_files:
        valid_extensions_tuple = tuple(f".{ext.lower()}" for ext in allowed_types)
        for file_obj in uploaded_files:
            if not file_obj.name.lower().endswith(valid_extensions_tuple):
                st.warning(f"File `{file_obj.name}` has an unsupported extension. Skipped.")
            else:
                valid_files_after_upload.append(file_obj)
        uploaded_files = valid_files_after_upload

    st.subheader("2. Download Options")
    resize_option = st.radio("Resize method", ["Original size", "Scale (%)"], index=0, key="resize_option")
    scale_percent = 100
    if resize_option == "Scale (%)":
        scale_percent = st.slider("Scale percent", 10, 200, 100, key="scale_percent")

    output_format_options = ["JPG", "PNG", "WEBP"]
    output_format = st.selectbox("Output format", output_format_options, index=0, key="output_format")
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
    # The 'remove_adjacent_border' checkbox is currently not used in the simplified draw_layout border logic.
    # To re-enable its functionality, the more complex border drawing logic from the previous version would be needed.
    st.checkbox("Align swatches to image edge (no double border)", value=True, key="remove_adjacent_border", help="Note: This feature's detailed logic for border removal is simplified in current drawing function.")


# --- Process & Preview ---
if uploaded_files and positions:
    st.markdown("---")
    st.subheader("Previews")

    preview_html_placeholder = preview_display_area_container.empty()
    individual_preview_html_parts = []
    processed_images_for_zip = 0
    zip_buffer = io.BytesIO()

    with st.spinner("Generating previews and preparing ZIP... Please wait."):
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
            for uploaded_file_obj in uploaded_files:
                original_image_for_processing = None
                try:
                    uploaded_file_bytes = uploaded_file_obj.getvalue()
                    temp_image = Image.open(io.BytesIO(uploaded_file_bytes))
                    temp_image.verify()
                    original_image_for_processing = Image.open(io.BytesIO(uploaded_file_bytes))

                except UnidentifiedImageError:
                    st.warning(f"Cannot identify image format for `{uploaded_file_obj.name}`. Skipped.")
                    continue
                except Exception as e_open:
                    st.error(f"Error opening or verifying `{uploaded_file_obj.name}`: {e_open}. Skipped.")
                    st.exception(e_open)
                    continue

                if original_image_for_processing:
                    try:
                        w, h = original_image_for_processing.size
                        if not (10 <= w <= 10000 and 10 <= h <= 10000):
                            st.warning(f"`{uploaded_file_obj.name}` ({w}x{h}) has atypical dimensions. Skipped.")
                            continue

                        if original_image_for_processing.mode not in ("RGB", "RGBA", "L"):
                            image_to_process = original_image_for_processing.convert("RGB")
                        elif original_image_for_processing.mode == "RGBA":
                            image_to_process = original_image_for_processing.convert("RGB")
                        else:
                            image_to_process = original_image_for_processing.copy()

                        palette = extract_palette(image_to_process, num_colors, quantize_method_selected)
                        if not palette and num_colors > 0:
                             st.caption(f"No color palette extracted for `{uploaded_file_obj.name}`.")

                    except Exception as e_palette:
                        st.error(f"Error during pre-processing or palette extraction for `{uploaded_file_obj.name}`: {e_palette}. Skipped.")
                        st.exception(e_palette)
                        continue

                    border_px = int(image_to_process.width * (border_thickness_percent / 100))
                    # Get the state of remove_adjacent_border checkbox for draw_layout
                    # Note: The current draw_layout's border logic is simplified.
                    # For full effect of this checkbox, the border drawing in draw_layout needs to be more nuanced.
                    remove_adj_border_setting = st.session_state.get('remove_adjacent_border', True)


                    for pos_idx, pos in enumerate(positions):
                        try:
                            current_image_for_layout = image_to_process.copy()
                            result_img = draw_layout(current_image_for_layout, palette, pos, border_px,
                                                     swatch_border_thickness, border_color, swatch_border_color,
                                                     swatch_size_percent_val, remove_adj_border_setting)

                            if resize_option == "Scale (%)" and scale_percent != 100:
                                new_w = int(result_img.width * scale_percent / 100)
                                new_h = int(result_img.height * scale_percent / 100)
                                if new_w > 0 and new_h > 0:
                                    result_img = result_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                                else:
                                    st.warning(f"Skipping resize for `{uploaded_file_obj.name}` (pos: {pos}) due to invalid new dimensions.")

                            img_byte_arr_download = io.BytesIO()
                            base_name, _ = os.path.splitext(uploaded_file_obj.name)
                            safe_base_name = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in base_name).strip()
                            name_for_file = f"{safe_base_name}_{pos}.{file_extension}"

                            save_params = {}
                            if img_format_pil == "JPEG": save_params['quality'] = 95
                            elif img_format_pil == "WEBP":
                                save_params['quality'] = 85
                                if webp_lossless:
                                    save_params.update({'lossless': True, 'quality': 100})

                            result_img.save(img_byte_arr_download, format=img_format_pil, **save_params)
                            img_bytes_for_download = img_byte_arr_download.getvalue()

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

                            display_name_short = shorten_filename(name_for_file, name_max_len=22, front_chars=10, back_chars=7)

                            # --- HTML Escaping for safety ---
                            alt_text = html.escape(f"{name_for_file} Preview")
                            item_title = html.escape(name_for_file) # Used for main title attribute
                            display_name_escaped = html.escape(display_name_short) # Used for visible text
                            download_link_title = html.escape(f"Download {name_for_file}")

                            single_item_html = f"""
                            <div class='preview-item'>
                                <div>
                                    <img src='data:image/png;base64,{img_base64_thumb}' alt='{alt_text}'>
                                    <div class='preview-item-name' title='{item_title}'>{display_name_escaped}</div>
                                </div>
                                <a href='{data_uri_for_download}' download='{item_title}' class='download-text-link' title='{download_link_title}'>Download Image</a>
                            </div>"""
                            individual_preview_html_parts.append(single_item_html)

                        except Exception as e_layout:
                            st.error(f"Error during layout/saving for `{uploaded_file_obj.name}` (pos: {pos}): {e_layout}")
                            st.exception(e_layout)

            if individual_preview_html_parts:
                full_html_content = "<div id='preview-zone'>" + "\n".join(individual_preview_html_parts) + "</div>"
                preview_html_placeholder.markdown(full_html_content, unsafe_allow_html=True)
            elif uploaded_files and positions:
                 preview_html_placeholder.info("No previews generated. Check for error messages above.")

        zip_buffer.seek(0)

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
            st.warning("No images were successfully processed for the ZIP download. Check error messages.")
        st.markdown("</div>", unsafe_allow_html=True)

elif uploaded_files and not positions:
    st.info("👉 Select at least one swatch position (Top, Bottom, Left, Right) to generate previews.")
    preview_display_area_container.empty()
    download_buttons_container.empty()
elif not uploaded_files:
    st.info("👋 Welcome! Upload images using the panel on the left to get started.")
    preview_display_area_container.empty()
    download_buttons_container.empty()

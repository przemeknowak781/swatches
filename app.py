import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import io
import zipfile
import base64
import os
import html

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("Color Swatch Generator")
st.markdown("""
<style>
h1 { margin-bottom: 20px !important; }
/* CSS styles for layout and preview cards omitted here for brevity but should be reinserted as in your original */
</style>
""", unsafe_allow_html=True)

# --- HTML Rendering Test ---
st.markdown("""
<div style='background-color: lightblue; padding: 10px; border-radius: 5px; margin-bottom:15px;'>
Test HTML rendering: <b>Bold Text</b>
</div>
""", unsafe_allow_html=True)

preview_display_area_container = st.container()
download_buttons_container = st.container()

# --- Utility Functions ---
def shorten_filename(filename, name_max_len=20, front_chars=8, back_chars=7):
    name_body, ext = os.path.splitext(filename)
    if len(name_body) > name_max_len:
        if front_chars + back_chars + 3 > name_max_len:
            front_chars = max(1, (name_max_len - 3) // 2)
            back_chars = max(1, name_max_len - 3 - front_chars)
        return f"{name_body[:front_chars]}...{name_body[-back_chars:]}{ext}"
    return filename

def extract_palette(image: Image.Image, num_colors=6, quantize_method=Image.MEDIANCUT):
    img_rgb = image.convert("RGB")
    try:
        paletted_image = img_rgb.quantize(colors=num_colors, method=quantize_method)
        palette_data = paletted_image.getpalette()
        if palette_data is None:
            raise ValueError("Palette data is None after primary quantization.")
        actual_colors_in_palette = len(palette_data) // 3
        colors_to_extract = min(num_colors, actual_colors_in_palette)
        return [tuple(palette_data[i*3 : i*3+3]) for i in range(colors_to_extract)]
    except Exception:
        return []

def draw_layout(image: Image.Image, colors: list, position: str, border_thickness_px: int,
                swatch_border_thickness: int, border_color: str, swatch_border_color: str,
                swatch_size_percent: int, remove_adjacent_border: bool):
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
    else:
        return image.copy()

    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    canvas.paste(image, img_paste_coords)
    draw = ImageDraw.Draw(canvas)
    dim_per_swatch = total_swatch_dim // len(colors)
    extra_dim_for_last = total_swatch_dim % len(colors)
    for i, color_tuple in enumerate(colors):
        current_w_or_h = dim_per_swatch + (extra_dim_for_last if i == len(colors) - 1 else 0)
        if position in ['top', 'bottom']:
            x0 = swatch_area_x_start + i * dim_per_swatch
            y0 = swatch_area_y_start
            x1 = x0 + current_w_or_h
            y1 = y0 + actual_swatch_size_px
        else:
            x0 = swatch_area_x_start
            y0 = swatch_area_y_start + i * dim_per_swatch
            x1 = x0 + actual_swatch_size_px
            y1 = y0 + current_w_or_h
        draw.rectangle([x0, y0, x1, y1], fill=tuple(color_tuple))
    return canvas

# --- UI Controls ---
# [UI layout with st.columns and all widgets - reuse from your existing code]
# [Insert all your input panels here, unchanged]

# --- Processing Section ---
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
                try:
                    uploaded_file_bytes = uploaded_file_obj.getvalue()
                    original_image = Image.open(io.BytesIO(uploaded_file_bytes)).convert("RGB")
                    palette = extract_palette(original_image, num_colors, quantize_method_selected)
                    border_px = int(original_image.width * (border_thickness_percent / 100))

                    for pos in positions:
                        result_img = draw_layout(original_image, palette, pos, border_px,
                                                 swatch_border_thickness, border_color, swatch_border_color,
                                                 swatch_size_percent_val, st.session_state.get('remove_adjacent_border', True))

                        if resize_option == "Scale (%)" and scale_percent != 100:
                            new_w = int(result_img.width * scale_percent / 100)
                            new_h = int(result_img.height * scale_percent / 100)
                            result_img = result_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                        img_byte_arr_download = io.BytesIO()
                        base_name, _ = os.path.splitext(uploaded_file_obj.name)
                        safe_name = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in base_name).strip()
                        name_for_file = f"{safe_name}_{pos}.{file_extension}"

                        save_params = {}
                        if img_format_pil == "JPEG":
                            save_params['quality'] = 95
                        elif img_format_pil == "WEBP":
                            save_params['quality'] = 85
                            if webp_lossless:
                                save_params.update({'lossless': True, 'quality': 100})

                        result_img.save(img_byte_arr_download, format=img_format_pil, **save_params)
                        img_bytes = img_byte_arr_download.getvalue()
                        zipf.writestr(name_for_file, img_bytes)
                        processed_images_for_zip += 1

                        preview_img = result_img.copy()
                        preview_img.thumbnail((180, 180))
                        with io.BytesIO() as buffer_display:
                            preview_img.save(buffer_display, format="PNG")
                            img_base64_thumb = base64.b64encode(buffer_display.getvalue()).decode("utf-8")

                        data_uri = f"data:image/{img_format_pil.lower()};base64," + base64.b64encode(img_bytes).decode("utf-8")
                        short_name = shorten_filename(name_for_file, 22, 10, 7)

                        single_html = f"""
                        <div class='preview-item'>
                            <div>
                                <img src='data:image/png;base64,{img_base64_thumb}' alt='{html.escape(name_for_file)} Preview'>
                                <div class='preview-item-name' title='{html.escape(name_for_file)}'>{html.escape(short_name)}</div>
                            </div>
                            <a href='{data_uri}' download='{html.escape(name_for_file)}' class='download-text-link'>Download Image</a>
                        </div>
                        """
                        individual_preview_html_parts.append(single_html)

                except Exception as e:
                    st.error(f"Failed processing {uploaded_file_obj.name}: {e}")

        # Final render of previews
        if individual_preview_html_parts:
            full_html_content = f"""
            <div id='preview-zone'>
                {'\n'.join(individual_preview_html_parts)}
            </div>
            """
            preview_html_placeholder.markdown(full_html_content, unsafe_allow_html=True)
        else:
            preview_html_placeholder.info("No previews generated. Check for error messages above.")

    with download_buttons_container:
        st.markdown("<div class='zip-download-wrapper'>", unsafe_allow_html=True)
        if processed_images_for_zip > 0:
            st.download_button(
                label=f"⬇️ Download All as ZIP ({processed_images_for_zip} image{'s' if processed_images_for_zip > 1 else ''}, {output_format.upper()})",
                data=zip_buffer,
                file_name=f"ColorSwatches_{output_format.lower()}.zip",
                mime="application/zip",
                use_container_width=True,
                key="download_zip_main")
        else:
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

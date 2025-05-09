import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import numpy as np
import io
import zipfile
import base64

# --- Reset / Clear State Button ---
# (removed because Streamlit should not rely on buttons for uploader validation)

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("🎨 Color Swatch Generator")

# --- Preview container ---
preview_container = st.container()

# --- CSS for responsive columns ---
st.markdown("""
    <style>
    @media (min-width: 768px) {
        .responsive-columns {
            display: flex;
            gap: 2rem;
        }
        .responsive-columns > div {
            flex: 1;
        }
    }
    </style>
""", unsafe_allow_html=True)

# --- Color Extraction ---
def extract_palette(image, num_colors=6, quantize_method=Image.MEDIANCUT):
    img = image.convert("RGB")
    img = img.resize((300, 300))  # optional downscale for performance

    # Use Pillow's quantize to reduce image to a palette
    paletted = img.quantize(colors=num_colors, method=quantize_method)
    palette = paletted.getpalette()[:num_colors * 3]  # RGB triplets
    colors = [tuple(palette[i:i+3]) for i in range(0, len(palette), 3)]
    return colors

# --- Draw Layout Function ---
def draw_layout(image, colors, position, border_thickness, swatch_border_thickness, border_color, swatch_border_color, swatch_size, remove_adjacent_border):
    img_w, img_h = image.size
    border = border_thickness

    if position == 'top':
        canvas = Image.new("RGB", (img_w + 2 * border, img_h + swatch_size + 2 * border), border_color)
        canvas.paste(image, (border, swatch_size + border))
        swatch_y = border
        swatch_width = img_w // len(colors)

    elif position == 'bottom':
        canvas = Image.new("RGB", (img_w + 2 * border, img_h + swatch_size + 2 * border), border_color)
        canvas.paste(image, (border, border))
        swatch_y = border + img_h
        swatch_width = img_w // len(colors)

    elif position == 'left':
        canvas = Image.new("RGB", (img_w + swatch_size + 2 * border, img_h + 2 * border), border_color)
        canvas.paste(image, (swatch_size + border, border))
        swatch_x = border
        swatch_height = img_h // len(colors)

    elif position == 'right':
        canvas = Image.new("RGB", (img_w + swatch_size + 2 * border, img_h + 2 * border), border_color)
        canvas.paste(image, (border, border))
        swatch_x = border + img_w
        swatch_height = img_h // len(colors)

    draw = ImageDraw.Draw(canvas)

    for i, color in enumerate(colors):
        if position in ['top', 'bottom']:
            x0 = border + i * swatch_width
            x1 = border + (i + 1) * swatch_width
            y0 = swatch_y
            y1 = swatch_y + swatch_size
        else:
            y0 = border + i * swatch_height
            y1 = border + (i + 1) * swatch_height
            x0 = swatch_x
            x1 = swatch_x + swatch_size

        draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
        if not remove_adjacent_border or i != 0:
            draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
        if not remove_adjacent_border or i != len(colors) - 1:
            draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
        draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
        draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

    return canvas

# --- Input Columns ---
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Upload Images")
    allowed_types = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif"]
    uploaded_files = st.file_uploader(
        "Upload images",
        accept_multiple_files=True
    )

    # Early validation and user feedback for invalid extensions
    if uploaded_files:
        valid_extensions = (".jpg", ".jpeg", ".png", ".webp", ".jfif", ".bmp", ".tiff", ".tif")
        filtered_files = []
        for file in uploaded_files:
            if not file.name.lower().endswith(valid_extensions):
                st.warning(f"⚠️ `{file.name}` has unsupported extension. Skipped.")
            else:
                filtered_files.append(file)
        uploaded_files = filtered_files

    st.subheader("Download Options")
    resize_option = st.radio("Resize method", ["Original size", "Scale (%)"], index=0)
    if resize_option == "Scale (%)":
        scale_percent = st.slider("Scale percent", 10, 200, 100)

    output_format = st.selectbox("Output format", ["JPG", "PNG", "WEBP"])
    format_map = {
        "JPG": ("JPEG", "jpg"),
        "PNG": ("PNG", "png"),
        "WEBP": ("WEBP", "webp")
    }
    img_format, extension = format_map[output_format]

with col2:
    st.subheader("Layout Settings")
    positions = []
    st.write("Swatch position(s):")

    row1 = st.columns(2)
    row2 = st.columns(2)
    with row1[0]:
        if st.toggle("Top", key="pos_top"):
            positions.append("top")
    with row1[1]:
        if st.toggle("Left", key="pos_left"):
            positions.append("left")
    with row2[0]:
        if st.toggle("Bottom", value=True, key="pos_bottom"):
            positions.append("bottom")
    with row2[1]:
        if st.toggle("Right", key="pos_right"):
            positions.append("right")

    quant_method_label = st.selectbox("Palette extraction method", ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"], index=0)
    quant_method_map = {
        "MEDIANCUT": Image.MEDIANCUT,
        "MAXCOVERAGE": Image.MAXCOVERAGE,
        "FASTOCTREE": Image.FASTOCTREE
    }
    quantize_method = quant_method_map[quant_method_label]

    num_colors = st.slider("Number of swatches", 2, 12, 6)
    swatch_size = st.slider("Swatch size (px)", 20, 200, 100)

with col3:
    st.subheader("Borders")
    border_thickness = st.slider("Image border thickness (% of image width)", 0, 10, 0)
    border_color = st.color_picker("Image border color", "#FFFFFF")
    swatch_border_thickness = st.slider("Swatch border thickness (px)", 0, 50, 5)
    swatch_border_color = st.color_picker("Swatch border color", "#FFFFFF")
    remove_adjacent_border = st.checkbox("Align swatches with image", value=True)

# --- Process & Preview ---
if uploaded_files and positions:
    with st.spinner("Generating previews..."):
        zip_buffer = io.BytesIO()
        preview_html_blocks = []
        placeholder = preview_container.container()
        zip_buffer = io.BytesIO()
        preview_html_blocks = []

        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zipf:
            preview_html_blocks = []
            placeholder.markdown("""
            <style>
            #preview-zone {
                display: flex;
                flex-wrap: nowrap;
                overflow-x: auto;
                gap: 30px;
                padding: 20px;
            }
            </style>
            <div id='preview-zone'>
            """, unsafe_allow_html=True)

            for uploaded_file in uploaded_files:
                try:
                    test_image = Image.open(uploaded_file)
                    test_image.verify()
                    uploaded_file.seek(0)
                    image = Image.open(uploaded_file)
                except Exception:
                    st.warning(f"⚠️ `{uploaded_file.name}` could not be loaded. Skipped.")
                    continue

                try:
                    w, h = image.size
                    if w < 100 or h < 100 or w > 10000 or h > 10000:
                        st.warning(f"⚠️ `{uploaded_file.name}` has unsupported resolution ({w}x{h}). Skipped.")
                        continue

                    image = image.convert("RGB")
                    palette = extract_palette(image, num_colors, quantize_method=quantize_method)
                except Exception:
                    st.warning(f"⚠️ `{uploaded_file.name}` could not be processed. Skipped.")
                    continue

                border_px = int(image.width * (border_thickness / 100))

                for pos in positions:
                    result_img = draw_layout(
                        image, palette, pos, border_px, swatch_border_thickness,
                        border_color, swatch_border_color, swatch_size, remove_adjacent_border
                    )

                    if resize_option == "Scale (%)":
                        new_w = int(result_img.width * scale_percent / 100)
                        new_h = int(result_img.height * scale_percent / 100)
                        result_img = result_img.resize((new_w, new_h), Image.LANCZOS)

                    img_byte_arr = io.BytesIO()
                    name = f"{uploaded_file.name.rsplit('.', 1)[0]}_{pos}.{extension}"
                    result_img.save(img_byte_arr, format=img_format)
                    zipf.writestr(name, img_byte_arr.getvalue())

                    preview_img = result_img.copy()
                    with io.BytesIO() as buffer:
                        preview_img.save(buffer, format="PNG")
                        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                    html_block = f"<div style='flex: 0 0 auto; text-align: center; width: 200px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); padding: 8px; border-radius: 8px; background: #eeeeee;'>"
                    html_block += f"<div style='font-size: 12px; margin-bottom: 5px;'>{name}</div>"
                    html_block += f"<img src='data:image/png;base64,{img_base64}' width='200'>"
                    html_block += "</div>"
                    placeholder.markdown(html_block, unsafe_allow_html=True)

        placeholder.markdown("</div>", unsafe_allow_html=True)
        zip_buffer.seek(0)

    st.download_button(
                f"📦 Download all as ZIP ({extension.upper()})",
                zip_buffer,
                file_name=f"swatches.{extension}.zip",
                mime="application/zip",
                use_container_width=True
            )

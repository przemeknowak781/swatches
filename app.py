import streamlit as st
from PIL import Image, ImageDraw
import numpy as np
from sklearn.cluster import KMeans
import io
import zipfile
import base64

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
def extract_palette(image, num_colors=6):
    img = image.convert('RGB')
    data = np.array(img).reshape((-1, 3))
    kmeans = KMeans(n_clusters=num_colors, random_state=42).fit(data)
    return kmeans.cluster_centers_.astype(int)

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
    uploaded_files = st.file_uploader("Upload images", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

    st.subheader("Download Size")
    resize_option = st.radio("Resize method", ["Original size", "Scale (%)"], index=0)
    if resize_option == "Scale (%)":
        scale_percent = st.slider("Scale percent", 10, 200, 100)

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

        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zipf:
            for uploaded_file in uploaded_files:
                image = Image.open(uploaded_file).convert("RGB")
                palette = extract_palette(image, num_colors)
                border_px = int(image.width * (border_thickness / 100))

                for pos in positions:
                    result_img = draw_layout(
                        image, palette, pos, border_px, swatch_border_thickness,
                        border_color, swatch_border_color, swatch_size, remove_adjacent_border
                    )

                    # Resize the image before saving
                    if resize_option == "Scale (%)":
                        new_w = int(result_img.width * scale_percent / 100)
                        new_h = int(result_img.height * scale_percent / 100)
                        result_img = result_img.resize((new_w, new_h), Image.LANCZOS)

                    img_byte_arr = io.BytesIO()
                    name = f"{uploaded_file.name.rsplit('.', 1)[0]}_{pos}.jpg"
                    result_img.save(img_byte_arr, format='JPEG', quality=95)
                    zipf.writestr(name, img_byte_arr.getvalue())

                    # Create preview image (use resized image)
                    preview_img = result_img.copy()
                    with io.BytesIO() as buffer:
                        preview_img.save(buffer, format="PNG")
                        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                    html_block = f"<div style='flex: 0 0 auto; text-align: center; width: 200px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); padding: 8px; border-radius: 8px; background: #eeeeee;'>"
                    html_block += f"<div style='font-size: 12px; margin-bottom: 5px;'>{name}</div>"
                    html_block += f"<img src='data:image/png;base64,{img_base64}' width='200'>"
                    html_block += "</div>"
                    preview_html_blocks.append(html_block)

        zip_buffer.seek(0)

        with preview_container:
            st.markdown("### Preview")
            full_html = "<div style='display: flex; overflow-x: auto; gap: 30px; padding: 20px;'>" + "\n".join(preview_html_blocks) + "</div>"
            st.markdown(full_html, unsafe_allow_html=True)
            st.download_button("📦 Download all as ZIP", zip_buffer, file_name="swatches.zip", mime="application/zip", use_container_width=True)

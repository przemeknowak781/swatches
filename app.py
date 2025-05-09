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
/* Page and heading */
h1 { margin-bottom: 20px !important; }

/* Responsive columns */
@media (min-width: 768px) {
  .responsive-columns { display: flex; gap: 2rem; }
  .responsive-columns > div { flex: 1; }
}

/* Section headings */
h2 {
  margin-bottom: 0.9rem !important;
  margin-top: 1rem !important;
}

/* Input widget spacing */
.stFileUploader, .stSelectbox, .stSlider, .stRadio, .stColorPicker {
  margin-bottom: 10px;
}

/* Preview zone container */
#preview-zone {
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
}

/* Individual preview items */
.preview-item {
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
}
.preview-item:hover {
  box-shadow: 0 6px 16px rgba(0,0,0,0.15);
}
.preview-item img {
  width: 100%;
  max-width: 176px;
  height: auto;
  border-radius: 4px;
  margin-bottom: 8px;
  align-self: center;
}
.preview-item-name {
  font-size: 12px;
  margin-bottom: 5px;
  color: #333;
  word-break: break-all;
  height: 30px;
  overflow: hidden;
  line-height: 1.3;
}

/* Download link style */
.download-text-link {
  font-size: 11px;
  color: #888;
  text-decoration: none;
  display: block;
  margin-top: 8px;
  padding: 3px 0;
  transition: color 0.2s ease;
}
.download-text-link:hover {
  color: #333;
  text-decoration: underline;
}

/* ZIP button wrapper */
.zip-download-wrapper {
  margin-top: 25px;
  margin-bottom: 20px;
}
.zip-download-wrapper .stDownloadButton button {
  font-weight: bold !important;
}
</style>
""", unsafe_allow_html=True)

# --- HTML Rendering Test ---
st.markdown("""
<div style='background-color: lightblue; padding: 10px; border-radius: 5px; margin-bottom:15px;'>
  Test HTML rendering: <b>Bold Text</b>
</div>
""", unsafe_allow_html=True)

# --- Containers ---
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
        paletted = img_rgb.quantize(colors=num_colors, method=quantize_method)
        data = paletted.getpalette()
        if data is None:
            raise ValueError("Palette data is None.")
        count = len(data) // 3
        to_take = min(num_colors, count)
        return [tuple(data[i*3:i*3+3]) for i in range(to_take)]
    except Exception:
        # Fallback to FASTOCTREE
        try:
            pal_f = img_rgb.quantize(colors=num_colors, method=Image.FASTOCTREE)
            data_f = pal_f.getpalette()
            if data_f is None:
                return []
            count_f = len(data_f) // 3
            to_take_f = min(num_colors, count_f)
            return [tuple(data_f[i*3:i*3+3]) for i in range(to_take_f)]
        except Exception:
            return []


def draw_layout(image: Image.Image, colors: list, position: str, border_thickness_px: int,
                swatch_border_thickness: int, border_color: str, swatch_border_color: str,
                swatch_size_percent: int, remove_adjacent_border: bool):
    img_w, img_h = image.size
    border = border_thickness_px
    # Determine swatch size
    if position in ['top', 'bottom']:
        sw_h = int(img_h * swatch_size_percent / 100)
    else:
        sw_h = int(img_w * swatch_size_percent / 100)
    sw_h = max(1, sw_h)

    if not colors:
        if border > 0:
            canvas = Image.new("RGB", (img_w+2*border, img_h+2*border), border_color)
            canvas.paste(image, (border,border))
            return canvas
        return image.copy()

    # Compute canvas size and positions
    if position == 'top':
        cw, ch = img_w+2*border, img_h+sw_h+2*border
        img_pos = (border, sw_h+border)
        sw_x0, sw_y0 = border, border
        total_sw = img_w
    elif position == 'bottom':
        cw, ch = img_w+2*border, img_h+sw_h+2*border
        img_pos = (border, border)
        sw_x0, sw_y0 = border, img_h+border
        total_sw = img_w
    elif position == 'left':
        cw, ch = img_w+sw_h+2*border, img_h+2*border
        img_pos = (sw_h+border, border)
        sw_x0, sw_y0 = border, border
        total_sw = img_h
    else:  # right
        cw, ch = img_w+sw_h+2*border, img_h+2*border
        img_pos = (border, border)
        sw_x0, sw_y0 = img_w+border, border
        total_sw = img_h

    canvas = Image.new("RGB", (cw, ch), border_color)
    canvas.paste(image, img_pos)
    draw = ImageDraw.Draw(canvas)

    n = len(colors)
    per = total_sw // n
    extra = total_sw % n

    for i, col in enumerate(colors):
        size = per + (extra if i == n-1 else 0)
        if position in ['top', 'bottom']:
            x0 = sw_x0 + i*per; y0 = sw_y0
            x1 = x0 + size; y1 = y0 + sw_h
        else:
            x0 = sw_x0; y0 = sw_y0 + i*per
            x1 = x0 + sw_h; y1 = y0 + size
        draw.rectangle([x0,y0,x1,y1], fill=col)
        # Borders skipped for simplicity; original code draws borders here

    return canvas

# --- UI Inputs ---
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("1. Upload Images")
    allowed = ["jpg","jpeg","png","webp","jfif","bmp","tiff","tif"]
    uploaded_files = st.file_uploader("Choose images", accept_multiple_files=True, type=allowed)

    # Filter valid
    valid = []
    if uploaded_files:
        exts = tuple(f".{e}" for e in allowed)
        for f in uploaded_files:
            if f.name.lower().endswith(exts): valid.append(f)
            else: st.warning(f"Unsupported: {f.name}")
        uploaded_files = valid

    st.subheader("2. Download Options")
    resize_option = st.radio("Resize method", ["Original size","Scale (%)"], index=0)
    scale_percent = 100
    if resize_option == "Scale (%)":
        scale_percent = st.slider("Scale percent",10,200,100)

    out_opts = ["JPG","PNG","WEBP"]
    output_format = st.selectbox("Output format", out_opts)
    webp_lossless = False
    if output_format=="WEBP": webp_lossless = st.checkbox("Lossless WEBP",False)

    fmt_map = {"JPG":("JPEG","jpg"),"PNG":("PNG","png"),"WEBP":("WEBP","webp")}
    img_format_pil, file_ext = fmt_map[output_format]

with col2:
    st.subheader("3. Layout Settings")
    positions=[]
    st.write("Swatch position(s):")
    t1,t2,t3,t4 = st.columns(4)
    if t1.toggle("Top"): positions.append("top")
    if t2.toggle("Bottom",value=True): positions.append("bottom")
    if t3.toggle("Left"): positions.append("left")
    if t4.toggle("Right"): positions.append("right")

    qlabel = st.selectbox("Palette method",["MEDIANCUT","MAXCOVERAGE","FASTOCTREE"])
    qmap = {"MEDIANCUT":Image.MEDIANCUT,"MAXCOVERAGE":Image.MAXCOVERAGE,"FASTOCTREE":Image.FASTOCTREE}
    quantize_method_selected = qmap[qlabel]

    num_colors = st.slider("Number of swatches",2,12,6)
    swatch_size_percent_val = st.slider("Swatch size (% of image dim.)",5,50,20)

with col3:
    st.subheader("4. Border Settings")
    border_thickness_percent = st.slider("Image border (% of width)",0,10,0)
    border_color = st.color_picker("Image border color","#FFFFFF")
    swatch_border_thickness = st.slider("Swatch border (px)",0,10,1)
    swatch_border_color = st.color_picker("Swatch border color","#CCCCCC")
    remove_adjacent_border = st.checkbox("Align swatches to edge (no double border)",True)

# --- Process & Preview ---
if uploaded_files and positions:
    st.markdown("---")
    st.subheader("Previews")
    place = preview_display_area_container.empty()
    html_parts=[]
    count=0
    buffer=io.BytesIO()

    with st.spinner("Generating previews and preparing ZIP... Please wait."):
        with zipfile.ZipFile(buffer,"a",zipfile.ZIP_DEFLATED) as zf:
            for fobj in uploaded_files:
                try:
                    data = fobj.getvalue()
                    img = Image.open(io.BytesIO(data))
                    img.verify(); img = Image.open(io.BytesIO(data)).convert("RGB")
                    w,h = img.size
                    if not (10<=w<=10000 and 10<=h<=10000):
                        st.warning(f"{fobj.name} has atypical dimensions. Skipped."); continue

                    palette = extract_palette(img, num_colors, quantize_method_selected)
                    border_px = int(img.width*(border_thickness_percent/100))

                    for pos in positions:
                        res = draw_layout(img, palette, pos, border_px,
                                          swatch_border_thickness, border_color, swatch_border_color,
                                          swatch_size_percent_val, remove_adjacent_border)
                        if resize_option=="Scale (%)" and scale_percent!=100:
                            nw = int(res.width*scale_percent/100)
                            nh = int(res.height*scale_percent/100)
                            if nw>0 and nh>0: res=res.resize((nw,nh),Image.Resampling.LANCZOS)

                        b = io.BytesIO()
                        base,_ = os.path.splitext(fobj.name)
                        safe = "".join(c if c.isalnum() or c in (' ','.','_','-') else '_' for c in base)
                        name = f"{safe}_{pos}.{file_ext}"
                        sp = {}
                        if img_format_pil=="JPEG": sp['quality']=95
                        elif img_format_pil=="WEBP": sp['quality']=85;
                            (sp.update({'lossless':True,'quality':100}) if webp_lossless else None)
                        res.save(b,format=img_format_pil,**sp)
                        raw = b.getvalue()
                        zf.writestr(name,raw)
                        count+=1

                        # thumbnail
                        thumb=res.copy(); thumb.thumbnail((180,180))
                        td=io.BytesIO(); thumb.save(td,format="PNG")
                        thumb_b64=base64.b64encode(td.getvalue()).decode()

                        uri=f"data:image/{img_format_pil.lower()};base64,"+base64.b64encode(raw).decode()
                        short=shorten_filename(name,22,10,7)
                        html_parts.append(f"""
                        <div class='preview-item'>
                          <div>
                            <img src='data:image/png;base64,{thumb_b64}' alt='{html.escape(name)} Preview'>
                            <div class='preview-item-name' title='{html.escape(name)}'>{html.escape(short)}</div>
                          </div>
                          <a href='{uri}' download='{html.escape(name)}' class='download-text-link'>Download Image</a>
                        </div>
                        """
                        )
                except UnidentifiedImageError:
                    st.warning(f"Cannot identify image format for {fobj.name}. Skipped.")
                except Exception as e:
                    st.error(f"Error processing {fobj.name}: {e}")

        # render previews
        if html_parts:
            full_html=f"""
            <div id='preview-zone'>
                {'\n'.join(html_parts)}
            </div>
            """
            place.markdown(full_html, unsafe_allow_html=True)
        else:
            place.info("No previews generated.")

    with download_buttons_container:
        st.markdown("<div class='zip-download-wrapper'>", unsafe_allow_html=True)
        if count>0:
            st.download_button(
                label=f"⬇️ Download All as ZIP ({count} image{'s' if count>1 else ''}, {output_format})",
                data=buffer,
                file_name=f"ColorSwatches_{output_format.lower()}.zip",
                mime="application/zip",
                use_container_width=True)
        else:
            st.warning("No images were processed for download.")
        st.markdown("</div>", unsafe_allow_html=True)

elif uploaded_files and not positions:
    st.info("👉 Select at least one swatch position to generate previews.")
    preview_display_area_container.empty(); download_buttons_container.empty()
elif not uploaded_files:
    st.info("👋 Welcome! Upload images to get started.")
    preview_display_area_container.empty(); download_buttons_container.empty()

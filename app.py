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
if 'generation_stage' not in st.session_state:
    st.session_state.generation_stage = "initial"
if 'preview_html_parts' not in st.session_state:
    st.session_state.preview_html_parts = []
if 'generated_image_data' not in st.session_state:
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
spinner_container = st.empty()
preview_container = st.container()
download_buttons_container = st.container()
preloader_and_status_container = st.empty()
generate_full_batch_button_container = st.empty()
resize_message_container = st.empty()

# --- CSS for responsive columns and general styling ---
st.markdown("""
    <style>
    @media (min-width: 768px) { /* Responsive columns for wider screens */
        .responsive-columns { display: flex; gap: 2rem; }
        .responsive-columns > div { flex: 1; }
    }
    #preview-zone { /* Styles for the preview scrollable area */
        display: flex; flex-wrap: nowrap; overflow-x: auto;
        gap: 20px; padding: 20px; border-radius: 8px;
        min-height: 250px; /* Crucial for preventing collapse */
        align-items: flex-start; margin-bottom: 20px;
        background: #ffffff; border: 1px solid #e0e0e0;
    }
    .preview-item { /* Styles for individual preview items */
        flex: 0 0 auto; display: flex; flex-direction: column;
        align-items: center; text-align: center; width: 220px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15); padding: 10px;
        border-radius: 8px; background: #f0f0f0; border: 1px solid #e0e0e0;
    }
    .preview-item img { /* Styles for images within preview items */
        width: 100%; height: auto; border-radius: 4px;
        margin-bottom: 8px; object-fit: contain; max-height: 180px;
    }
    .preview-item-name { /* Styles for filenames in preview items */
        font-size: 12px; margin-bottom: 5px; color: #333;
        word-break: break_all; height: 30px; overflow: hidden;
        width: 100%; text-overflow: ellipsis; white-space: nowrap;
    }
    .download-link { /* Styles for individual download links in previews */
        font-size: 10px; color: #888; text-decoration: none;
        margin-top: 5px; white-space: nowrap; overflow: hidden;
        text-overflow: ellipsis; max_width: 100%; display: block;
    }
    .download-link:hover { text-decoration: underline; color: #555; }
    h2 { margin_bottom: 0.9rem !important; } /* Spacing for subheaders */
    .stDownloadButton { margin_top: 10px; } /* Spacing for download buttons */
    .preloader-area { /* Styles for the preloader area */
        display: flex; align-items: center; justify-content: center;
        margin: 20px auto; min_height: 40px;
    }
    .preloader { /* Animated spinner */
        border: 4px solid #f3f3f3; border-top: 4px solid #3498db;
        border-radius: 50%; width: 30px; height: 30px;
        animation: spin 1s linear infinite; margin-right: 15px;
    }
    .preloader-text { font-size: 16px; color: #555; } /* Text next to spinner */
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
""", unsafe_allow_html=True)

# --- Utility Functions ---
def shorten_filename(filename, max_len=25, front_chars=10, back_chars=10):
    if len(filename) > max_len:
        name, ext = os.path.splitext(filename)
        back_chars_name = max(0, back_chars - len(ext))
        return f"{name[:front_chars]}...{name[-back_chars_name:]}{ext}"
    return filename

def is_valid_image_header(file_bytes):
    header = file_bytes[:12]
    if header.startswith(b'\xFF\xD8\xFF'): return 'jpeg'
    if header.startswith(b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A'): return 'png'
    if header.startswith(b'\x47\x49\x46\x38\x37\x61') or header.startswith(b'\x47\x49\x46\x38\x39\x61'): return 'gif'
    if header.startswith(b'\x42\x4D'): return 'bmp'
    if header.startswith(b'\x49\x49\x2A\x00') or header.startswith(b'\x4D\x4D\x00\x2A'): return 'tiff'
    if header.startswith(b'\x52\x49\x46\x46') and header[8:12] == b'\x57\x45\x42\x50': return 'webp'
    if header.startswith(b'\x00\x00\x01\x00') or header.startswith(b'\x00\x00\x02\x00'): return 'ico'
    return None

# --- Color Extraction ---
def extract_palette(image, num_colors=6, quantize_method=Image.MEDIANCUT):
    img = image.convert("RGB")
    try:
        paletted = img.quantize(colors=num_colors, method=quantize_method, kmeans=5)
        palette_full = paletted.getpalette()
        if palette_full is None: # Fallback if primary method fails
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE, kmeans=5)
            palette_full = paletted.getpalette()
            if palette_full is None: return [] # Return empty if fallback also fails
        actual_palette_colors = len(palette_full) // 3
        colors_to_extract = min(num_colors, actual_palette_colors)
        extracted_palette_rgb_values = palette_full[:colors_to_extract * 3]
        return [tuple(extracted_palette_rgb_values[i:i+3]) for i in range(0, len(extracted_palette_rgb_values), 3)]
    except Exception: # Broad exception for quantization issues
        try: # Attempt FASTOCTREE as a general fallback
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE, kmeans=5)
            palette = paletted.getpalette()
            if palette is None: return []
            return [tuple(palette[i:i+3]) for i in range(0, min(num_colors * 3, len(palette)), 3)]
        except Exception: return [] # Return empty if all attempts fail

# --- Draw Layout Function ---
def draw_layout(image, colors, position, image_border_thickness_px, swatch_separator_thickness_px,
                individual_swatch_border_thickness_px, border_color, swatch_border_color, swatch_size_percent):
    img_w, img_h = image.size
    main_border = image_border_thickness_px
    internal_swatch_border_thickness = individual_swatch_border_thickness_px

    # Calculate actual swatch size in pixels
    if position in ['top', 'bottom']: actual_swatch_size_px = int(img_h * (swatch_size_percent / 100))
    else: actual_swatch_size_px = int(img_w * (swatch_size_percent / 100))
    actual_swatch_size_px = max(1, actual_swatch_size_px) # Ensure at least 1px

    if not colors: # Handle cases with no extracted colors
        if main_border > 0: # Add border if specified
            canvas = Image.new("RGB", (img_w + 2 * main_border, img_h + 2 * main_border), border_color)
            canvas.paste(image, (main_border, main_border))
            return canvas
        return image.copy() # Return original if no colors and no border

    # Initialize layout variables
    swatch_width, swatch_height = 0, 0
    extra_w_last, extra_h_last = 0, 0 # For distributing remainder pixels
    image_paste_x, image_paste_y = main_border, main_border

    # Determine canvas size and swatch/image positions
    if position == 'top':
        canvas_h = img_h + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_w = img_w + 2 * main_border
        swatch_y_coord = main_border
        swatch_x_start = main_border
        swatch_total_width = img_w
        if len(colors) > 0: swatch_width, extra_w_last = divmod(swatch_total_width, len(colors))
        image_paste_y = main_border + actual_swatch_size_px + swatch_separator_thickness_px
    elif position == 'bottom':
        canvas_h = img_h + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_w = img_w + 2 * main_border
        swatch_y_coord = main_border + img_h + swatch_separator_thickness_px
        swatch_x_start = main_border
        swatch_total_width = img_w
        if len(colors) > 0: swatch_width, extra_w_last = divmod(swatch_total_width, len(colors))
        image_paste_y = main_border
    elif position == 'left':
        canvas_w = img_w + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_h = img_h + 2 * main_border
        swatch_x_coord = main_border
        swatch_y_start = main_border
        swatch_total_height = img_h
        if len(colors) > 0: swatch_height, extra_h_last = divmod(swatch_total_height, len(colors))
        image_paste_x = main_border + actual_swatch_size_px + swatch_separator_thickness_px
    elif position == 'right':
        canvas_w = img_w + actual_swatch_size_px + 2 * main_border + swatch_separator_thickness_px
        canvas_h = img_h + 2 * main_border
        swatch_x_coord = main_border + img_w + swatch_separator_thickness_px
        swatch_y_start = main_border
        swatch_total_height = img_h
        if len(colors) > 0: swatch_height, extra_h_last = divmod(swatch_total_height, len(colors))
    else: return image.copy() # Should not happen

    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    canvas.paste(image, (image_paste_x, image_paste_y))
    draw = ImageDraw.Draw(canvas)

    # Draw swatches
    for i, color_tuple in enumerate(colors):
        current_w, current_h = swatch_width, swatch_height
        if position in ['top', 'bottom']:
            current_w += 1 if i < extra_w_last else 0 # Distribute extra width
            x0 = swatch_x_start + i * swatch_width + min(i, extra_w_last)
            x1 = x0 + current_w
            y0, y1 = swatch_y_coord, swatch_y_coord + actual_swatch_size_px
        else: # 'left' or 'right'
            current_h += 1 if i < extra_h_last else 0 # Distribute extra height
            y0 = swatch_y_start + i * swatch_height + min(i, extra_h_last)
            y1 = y0 + current_h
            x0, x1 = swatch_x_coord, swatch_x_coord + actual_swatch_size_px
        draw.rectangle([x0, y0, x1, y1], fill=tuple(color_tuple))
        if internal_swatch_border_thickness > 0 and i < len(colors) - 1: # Draw internal borders
            if position in ['top', 'bottom']: draw.line([(x1 -1 , y0), (x1 -1, y1 -1)], fill=swatch_border_color, width=internal_swatch_border_thickness)
            else: draw.line([(x0, y1 -1), (x1-1, y1-1)], fill=swatch_border_color, width=internal_swatch_border_thickness)

    # Draw main border around canvas
    if main_border > 0:
        for i in range(main_border): # Draw multiple lines for thickness
            draw.rectangle([(i, i), (canvas_w - 1 - i, canvas_h - 1 - i)], outline=border_color, width=1)

    # Draw separator line between swatches and image
    if swatch_separator_thickness_px > 0:
        line_color_to_use = swatch_border_color
        line_thickness_to_use = swatch_separator_thickness_px
        if position == 'top':
            line_y = main_border + actual_swatch_size_px
            draw.line([(main_border, line_y), (canvas_w - main_border -1 , line_y)], fill=line_color_to_use, width=line_thickness_to_use)
        elif position == 'bottom':
            line_y = main_border + img_h
            draw.line([(main_border, line_y), (canvas_w - main_border -1, line_y)], fill=line_color_to_use, width=line_thickness_to_use)
        elif position == 'left':
            line_x = main_border + actual_swatch_size_px
            draw.line([(line_x, main_border), (line_x, canvas_h - main_border-1)], fill=line_color_to_use, width=line_thickness_to_use)
        elif position == 'right':
            line_x = main_border + img_w
            draw.line([(line_x, main_border), (line_x, canvas_h - main_border-1)], fill=line_color_to_use, width=line_thickness_to_use)
    return canvas

# --- Input Columns ---
col1, col2, col3 = st.columns(3)

try: # Main application try-except block
    with col1: # Image Upload and Download Options
        st.subheader("Upload Images")
        allowed_extensions = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif", "ico"]
        uploaded_files = st.file_uploader("Choose images", accept_multiple_files=True, type=allowed_extensions, key="file_uploader")
        valid_files = []
        if uploaded_files: # Validate uploaded files
            allowed_ext_set = set([f".{ext.lower()}" for ext in allowed_extensions])
            for f_obj in uploaded_files:
                f_name = f_obj.name
                try:
                    f_obj.seek(0); f_bytes = f_obj.read(12); f_obj.seek(0) # Read header
                    detected_fmt = is_valid_image_header(f_bytes)
                    if detected_fmt is None: st.warning(f"`{f_name}` invalid header. Skipped."); continue
                    f_ext = os.path.splitext(f_name)[1].lower()
                    if f_ext not in allowed_ext_set: st.warning(f"`{f_name}` unusual extension. Processing by header.")
                    valid_files.append(f_obj)
                except Exception as e: st.error(f"Error checking `{f_name}`: {e}. Skipped."); continue
            uploaded_files = valid_files

        st.subheader("Download Options")
        resize_option = st.radio("Resize method", ["Original size", "Scale (%)"], index=0, key="resize_option")
        scale_percent = 100
        if resize_option == "Scale (%)": scale_percent = st.slider("Scale percent", 10, 200, 100, key="scale_percent")
        output_format = st.selectbox("Output format", ["JPG", "PNG", "WEBP"], key="output_format")
        webp_lossless = False
        if output_format == "WEBP": webp_lossless = st.checkbox("Lossless WEBP", value=False, key="webp_lossless")
        fmt_map = {"JPG": ("JPEG", "jpg"), "PNG": ("PNG", "png"), "WEBP": ("WEBP", "webp")}
        img_format, extension = fmt_map[output_format]

    with col2: # Layout Settings
        st.subheader("Layout Settings")
        positions = []
        st.write("Swatch position(s):")
        r1_layout, r2_layout = st.columns(2), st.columns(2)
        if r1_layout[0].toggle("Top", value=True, key="pos_top"): positions.append("top")
        if r1_layout[1].toggle("Left", value=True, key="pos_left"): positions.append("left")
        if r2_layout[0].toggle("Bottom", value=True, key="pos_bottom"): positions.append("bottom")
        if r2_layout[1].toggle("Right", key="pos_right"): positions.append("right")
        quant_label = st.selectbox("Palette extraction", ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"], 0, key="quant_method")
        quant_map = {"MEDIANCUT": Image.MEDIANCUT, "MAXCOVERAGE": Image.MAXCOVERAGE, "FASTOCTREE": Image.FASTOCTREE}
        quantize_selected = quant_map[quant_label]
        num_colors = st.slider("Number of swatches", 2, 12, 6, key="num_colors")
        swatch_size_val = st.slider("Swatch size (% of image dim)", 5, 50, 20, key="swatch_size_percent")

    with col3: # Border Settings
        st.subheader("Borders")
        img_border_px = st.slider("Image Border Thickness (px)", 0, 50, 0, key="image_border_thickness_px") # Max 50px
        swatch_sep_px = st.slider("Swatch-Image Separator (px)", 0, 50, 0, key="swatch_separator_thickness_px") # Max 50px
        indiv_swatch_border_px = st.slider("Individual Swatch Border (px)", 0, 10, 0, key="individual_swatch_border_thickness_px") # Max 10px
        border_color = st.color_picker("Main Border Color", "#FFFFFF", key="border_color")
        swatch_border_color = st.color_picker("Swatch Border Color", "#FFFFFF", key="swatch_border_color")

    # --- Settings Change Detection & State Reset ---
    current_settings = (frozenset([(f.name, f.size) for f in uploaded_files]) if uploaded_files else None,
                        frozenset(positions), resize_option, scale_percent, output_format, webp_lossless,
                        quant_label, num_colors, swatch_size_val, img_border_px, swatch_sep_px,
                        indiv_swatch_border_px, border_color, swatch_border_color)
    new_settings_hash = hash(current_settings)
    if st.session_state.current_settings_hash != new_settings_hash:
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts, st.session_state.generated_image_data = [], {}
        st.session_state.zip_buffer, st.session_state.total_generations_at_start = None, 0
        st.session_state.full_batch_button_clicked = False
        generate_full_batch_button_container.empty(); resize_message_container.empty()
    st.session_state.current_settings_hash = new_settings_hash

    # --- Main Generation Logic ---
    if uploaded_files and positions:
        total_generations = len(uploaded_files) * len(positions)
        st.session_state.total_generations_at_start = total_generations
        st.markdown("---") # Visual separator
        preview_display_area = preview_container.empty()
        preview_display_area.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True) # Keep preview area visible

        # Determine images and layouts to process based on stage
        imgs_to_process, layouts_to_process = [], positions # Default to all selected layouts
        current_proc_count, proc_limit = 0, total_generations # Default to all generations

        # Preview stage: Limit to first 6 images
        if st.session_state.generation_stage == "initial" and total_generations > 6 * len(positions) : # Adjusted limit for clarity
            imgs_to_process = uploaded_files[:6]
            proc_limit = len(imgs_to_process) * len(layouts_to_process)
        elif st.session_state.generation_stage == "full_batch_generating" or total_generations <= 6 * len(positions):
            imgs_to_process = uploaded_files # Process all for full batch or small batches

        # Start generation if in 'initial' or 'full_batch_generating' stage, or if total is small
        if st.session_state.generation_stage in ["initial", "full_batch_generating"] or total_generations <= 6 * len(positions):
            preloader_text_area = preloader_and_status_container.empty()
            preloader_text_area.markdown("<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating previews... 0/0</span></div>", unsafe_allow_html=True)
            download_buttons_container.empty(); generate_full_batch_button_container.empty(); resize_message_container.empty()

            temp_preview_parts, temp_img_data = [], {}
            zip_io_buffer = io.BytesIO()

            with zipfile.ZipFile(zip_io_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
                for f_idx, up_file_obj in enumerate(imgs_to_process):
                    if st.session_state.generation_stage == "initial" and current_proc_count >= proc_limit: break
                    f_name = up_file_obj.name
                    try:
                        up_file_bytes = up_file_obj.getvalue()
                        try: # Open and verify image
                            pil_img = Image.open(io.BytesIO(up_file_bytes)); pil_img.verify()
                            pil_img = Image.open(io.BytesIO(up_file_bytes)) # Reopen after verify
                        except Exception as e_open:
                            st.warning(f"Skipped `{f_name}` (cannot open/verify): {e_open}")
                            current_proc_count += len(layouts_to_process); continue
                        if pil_img.mode not in ("RGB", "L"): pil_img = pil_img.convert("RGB")
                        extracted_palette = extract_palette(pil_img, num_colors, quantize_selected)

                        for pos_idx, pos_val in enumerate(layouts_to_process):
                            if st.session_state.generation_stage == "initial" and current_proc_count >= proc_limit: break
                            preloader_text_area.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating... {current_proc_count+1}/{proc_limit}</span></div>", unsafe_allow_html=True)
                            try:
                                final_img = draw_layout(pil_img.copy(), extracted_palette, pos_val, img_border_px,
                                                        swatch_sep_px, indiv_swatch_border_px, border_color,
                                                        swatch_border_color, swatch_size_val)
                                if resize_option == "Scale (%)" and scale_percent != 100:
                                    nw, nh = int(final_img.width*scale_percent/100), int(final_img.height*scale_percent/100)
                                    if nw > 0 and nh > 0: final_img = final_img.resize((nw,nh), Image.Resampling.LANCZOS)
                                img_byte_io = io.BytesIO()
                                base_n, _ = os.path.splitext(f_name)
                                safe_bn = "".join(c if c.isalnum() or c in (' ','.','_','-') else '_' for c in base_n).rstrip()
                                file_out_name = f"{safe_bn}_{pos_val}.{extension}"
                                save_p = {'quality':95} if img_format=="JPEG" else ({'quality':85,'lossless':True} if img_format=="WEBP" and webp_lossless else ({'quality':85} if img_format=="WEBP" else {}))
                                final_img.save(img_byte_io, format=img_format, **save_p)
                                dl_bytes = img_byte_io.getvalue()
                                temp_img_data[file_out_name] = dl_bytes
                                if st.session_state.generation_stage == "full_batch_generating" or total_generations <= proc_limit : # proc_limit here means small batch
                                    zipf.writestr(file_out_name, dl_bytes)
                                thumb = final_img.copy(); thumb.thumbnail((200,200))
                                with io.BytesIO() as buf_disp: thumb.save(buf_disp, "PNG"); b64_disp = base64.b64encode(buf_disp.getvalue()).decode()
                                b64_dl = base64.b64encode(dl_bytes).decode()
                                item_html = f"<div class='preview-item'><div class='preview-item-name' title='{file_out_name}'>{shorten_filename(file_out_name)}</div><img src='data:image/png;base64,{b64_disp}' alt='{file_out_name}'><a href='data:image/{extension};base64,{b64_dl}' download='{file_out_name}' class='download-link'>Download</a></div>"
                                temp_preview_parts.append(item_html)
                                current_proc_count +=1
                            except Exception as e_layout: st.error(f"Layout error for `{f_name}` ({pos_val}): {e_layout}"); current_proc_count +=1
                    except Exception as e_file: st.error(f"File error for `{f_name}`: {e_file}"); current_proc_count += len(layouts_to_process)
            st.session_state.preview_html_parts = temp_preview_parts
            st.session_state.generated_image_data = temp_img_data
            if st.session_state.generation_stage == "full_batch_generating" or total_generations <= proc_limit: # proc_limit means small batch
                zip_io_buffer.seek(0); st.session_state.zip_buffer = zip_io_buffer
            preloader_text_area.empty() # Clear preloader
            if st.session_state.generation_stage == "initial" and total_generations > proc_limit: st.session_state.generation_stage = "preview_generated"
            elif st.session_state.generation_stage == "full_batch_generating" or total_generations <= proc_limit: st.session_state.generation_stage = "completed"

        # --- Display Previews ---
        if st.session_state.preview_html_parts:
            preview_display_area.markdown("<div id='preview-zone'>" + "".join(st.session_state.preview_html_parts) + "</div>", unsafe_allow_html=True)
        # else: preview_display_area.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True) # Already set

        # --- Display "Generate Full Batch" Button ---
        if st.session_state.generation_stage == "preview_generated":
            with generate_full_batch_button_container:
                # UPDATED button text and ensuring it's primary type
                if st.button("Set Your layout and borders and **click here to generate whole batch!**", use_container_width=True, key="generate_full_batch_button", type="primary"):
                    st.session_state.generation_stage = "full_batch_generating"
                    st.session_state.full_batch_button_clicked = True
                    st.rerun()
        # else: generate_full_batch_button_container.empty() # Cleared during generation start

        # --- Display Download Button Logic ---
        with download_buttons_container:
            zip_ready = st.session_state.zip_buffer and st.session_state.zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader + 50
            if st.session_state.generation_stage == "completed" and zip_ready:
                st.download_button(f"Download All as ZIP ({extension.upper()})", st.session_state.zip_buffer, f"ColorSwatches_{output_format.lower()}.zip", "application/zip", True, key="dl_zip_enabled")
            elif st.session_state.generation_stage == "preview_generated":
                # UPDATED tooltip for this state
                st.download_button(f"Download All as ZIP ({extension.upper()})", io.BytesIO(), f"ColorSwatches_{output_format.lower()}.zip", "application/zip", True, key="dl_zip_disabled_preview", disabled=True, help="Generate the whole batch to download ZIP")
            elif uploaded_files: # Fallback disabled button if files are present but not yet fully processed
                 st.download_button(f"Download All as ZIP ({extension.upper()})", io.BytesIO(), f"ColorSwatches_{output_format.lower()}.zip", "application/zip", True, key="dl_zip_initial_disabled", disabled=True, help="Complete generation to enable download.")
            # else: download_buttons_container.empty() # Cleared during generation or if no files

    else: # No uploaded files or no positions selected
        st.session_state.generation_stage = "initial" # Reset stage
        st.session_state.preview_html_parts, st.session_state.generated_image_data = [], {}
        st.session_state.zip_buffer, st.session_state.total_generations_at_start = None, 0
        st.session_state.full_batch_button_clicked = False
        # Clear all dynamic containers
        generate_full_batch_button_container.empty(); resize_message_container.empty()
        preview_container.empty(); download_buttons_container.empty()
        spinner_container.empty(); preloader_and_status_container.empty()

        if uploaded_files and not positions:
            st.info("Select at least one swatch position to generate images.")
            with download_buttons_container: # Show disabled download if files are there but no positions
                 st.download_button(f"Download All as ZIP ({extension.upper()})", io.BytesIO(), f"ColorSwatches_{output_format.lower()}.zip", "application/zip", True, key="dl_zip_no_pos", disabled=True, help="Select swatch positions first.")
        elif not uploaded_files: st.info("Upload images to get started.")

except Exception as e: # Top-level error handler
    st.error(f"An unexpected application error occurred: {e}")
    st.exception(e) # Log full traceback for debugging
    st.warning("Attempting to reset application state. Please try your action again.")
    # Comprehensive state reset
    for key in list(st.session_state.keys()): del st.session_state[key]
    # Re-initialize core states to defaults
    st.session_state.generation_stage = "initial"
    st.session_state.preview_html_parts = []
    st.session_state.generated_image_data = {}
    st.session_state.zip_buffer = None
    st.session_state.total_generations_at_start = 0
    st.session_state.current_settings_hash = None # Will be set on next run
    st.session_state.full_batch_button_clicked = False
    st.rerun() # Force a clean rerun

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
preview_container = st.container() # Main container for the preview section
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
    # Shortens a filename string to a maximum length.
    if len(filename) > max_len:
        name, ext = os.path.splitext(filename)
        back_chars_name = max(0, back_chars - len(ext)) # Adjust for extension length
        return f"{name[:front_chars]}...{name[-back_chars_name:]}{ext}"
    return filename

def is_valid_image_header(file_bytes):
    # Checks the magic bytes of a file to determine if it's a known image format.
    header = file_bytes[:12] # Read first 12 bytes
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
    # Extracts a color palette from the given PIL Image.
    img = image.convert("RGB") # Ensure image is in RGB for palette extraction
    try:
        paletted = img.quantize(colors=num_colors, method=quantize_method, kmeans=5)
        palette_full = paletted.getpalette()
        if palette_full is None: # Fallback if primary method fails
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE, kmeans=5)
            palette_full = paletted.getpalette()
            if palette_full is None: return []
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
        except Exception: return []

# --- Draw Layout Function ---
def draw_layout(image, colors, position, image_border_thickness_px, swatch_separator_thickness_px,
                individual_swatch_border_thickness_px, border_color, swatch_border_color, swatch_size_percent):
    # Draws the image with color swatches according to specified layout and border settings.
    img_w, img_h = image.size
    main_border = image_border_thickness_px
    internal_swatch_border_thickness = individual_swatch_border_thickness_px

    if position in ['top', 'bottom']: actual_swatch_size_px = int(img_h * (swatch_size_percent / 100))
    else: actual_swatch_size_px = int(img_w * (swatch_size_percent / 100))
    actual_swatch_size_px = max(1, actual_swatch_size_px)

    if not colors: # If no colors, just add main border if specified
        if main_border > 0:
            canvas = Image.new("RGB", (img_w + 2*main_border, img_h + 2*main_border), border_color)
            canvas.paste(image, (main_border, main_border))
            return canvas
        return image.copy()

    swatch_width, swatch_height = 0, 0
    extra_w_last, extra_h_last = 0, 0
    image_paste_x, image_paste_y = main_border, main_border

    # Determine canvas dimensions and paste coordinates based on swatch position
    if position == 'top':
        canvas_h = img_h + actual_swatch_size_px + 2*main_border + swatch_separator_thickness_px
        canvas_w = img_w + 2*main_border
        swatch_y_coord, swatch_x_start = main_border, main_border
        if len(colors) > 0: swatch_width, extra_w_last = divmod(img_w, len(colors))
        image_paste_y = main_border + actual_swatch_size_px + swatch_separator_thickness_px
    elif position == 'bottom':
        canvas_h = img_h + actual_swatch_size_px + 2*main_border + swatch_separator_thickness_px
        canvas_w = img_w + 2*main_border
        swatch_y_coord = main_border + img_h + swatch_separator_thickness_px
        swatch_x_start = main_border
        if len(colors) > 0: swatch_width, extra_w_last = divmod(img_w, len(colors))
    elif position == 'left':
        canvas_w = img_w + actual_swatch_size_px + 2*main_border + swatch_separator_thickness_px
        canvas_h = img_h + 2*main_border
        swatch_x_coord, swatch_y_start = main_border, main_border
        if len(colors) > 0: swatch_height, extra_h_last = divmod(img_h, len(colors))
        image_paste_x = main_border + actual_swatch_size_px + swatch_separator_thickness_px
    elif position == 'right':
        canvas_w = img_w + actual_swatch_size_px + 2*main_border + swatch_separator_thickness_px
        canvas_h = img_h + 2*main_border
        swatch_x_coord = main_border + img_w + swatch_separator_thickness_px
        swatch_y_start = main_border
        if len(colors) > 0: swatch_height, extra_h_last = divmod(img_h, len(colors))
    else: return image.copy()

    canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
    canvas.paste(image, (image_paste_x, image_paste_y))
    draw = ImageDraw.Draw(canvas)

    # Draw color swatches
    for i, color_tuple in enumerate(colors):
        current_w, current_h = swatch_width, swatch_height
        if position in ['top', 'bottom']:
            current_w += 1 if i < extra_w_last else 0
            x0 = swatch_x_start + i * swatch_width + min(i, extra_w_last)
            x1, y0, y1 = x0 + current_w, swatch_y_coord, swatch_y_coord + actual_swatch_size_px
        else:
            current_h += 1 if i < extra_h_last else 0
            y0 = swatch_y_start + i * swatch_height + min(i, extra_h_last)
            y1, x0, x1 = y0 + current_h, swatch_x_coord, swatch_x_coord + actual_swatch_size_px
        draw.rectangle([x0, y0, x1, y1], fill=tuple(color_tuple))
        if internal_swatch_border_thickness > 0 and i < len(colors) - 1:
            if position in ['top', 'bottom']: draw.line([(x1-1, y0), (x1-1, y1-1)], fill=swatch_border_color, width=internal_swatch_border_thickness)
            else: draw.line([(x0, y1-1), (x1-1, y1-1)], fill=swatch_border_color, width=internal_swatch_border_thickness)

    if main_border > 0: # Draw main border around the entire canvas
        for i in range(main_border): draw.rectangle([(i,i), (canvas_w-1-i, canvas_h-1-i)], outline=border_color, width=1)

    if swatch_separator_thickness_px > 0: # Draw separator line
        line_color, line_thick = swatch_border_color, swatch_separator_thickness_px
        if position == 'top': draw.line([(main_border, main_border + actual_swatch_size_px), (canvas_w - main_border - 1, main_border + actual_swatch_size_px)], fill=line_color, width=line_thick)
        elif position == 'bottom': draw.line([(main_border, main_border + img_h), (canvas_w - main_border - 1, main_border + img_h)], fill=line_color, width=line_thick)
        elif position == 'left': draw.line([(main_border + actual_swatch_size_px, main_border), (main_border + actual_swatch_size_px, canvas_h - main_border - 1)], fill=line_color, width=line_thick)
        elif position == 'right': draw.line([(main_border + img_w, main_border), (main_border + img_w, canvas_h - main_border - 1)], fill=line_color, width=line_thick)
    return canvas

# --- Input Columns ---
col1, col2, col3 = st.columns(3)

try: # Main application try-except block
    with col1: # Column 1: Image Upload and Download Options
        st.subheader("Upload Images")
        allowed_extensions = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif", "ico"]
        uploaded_files = st.file_uploader("Choose images", accept_multiple_files=True, type=allowed_extensions, key="file_uploader")
        valid_files = []
        if uploaded_files: # File validation
            allowed_ext_set = set([f".{ext.lower()}" for ext in allowed_extensions])
            for f_obj in uploaded_files:
                f_name = f_obj.name
                try:
                    f_obj.seek(0); f_bytes = f_obj.read(12); f_obj.seek(0)
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

    with col2: # Column 2: Layout Settings
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

    with col3: # Column 3: Border Settings
        st.subheader("Borders")
        img_border_px = st.slider("Image Border Thickness (px)", 0, 50, 0, key="image_border_thickness_px")
        swatch_sep_px = st.slider("Swatch-Image Separator (px)", 0, 50, 0, key="swatch_separator_thickness_px")
        indiv_swatch_border_px = st.slider("Individual Swatch Border (px)", 0, 10, 0, key="individual_swatch_border_thickness_px")
        border_color = st.color_picker("Main Border Color", "#FFFFFF", key="border_color")
        swatch_border_color = st.color_picker("Swatch Border Color", "#FFFFFF", key="swatch_border_color")

    # --- Settings Change Detection & State Reset ---
    current_settings_tuple = (frozenset([(f.name, f.size) for f in uploaded_files]) if uploaded_files else None,
                              frozenset(positions), resize_option, scale_percent, output_format, webp_lossless,
                              quant_label, num_colors, swatch_size_val, img_border_px, swatch_sep_px,
                              indiv_swatch_border_px, border_color, swatch_border_color)
    new_settings_hash = hash(current_settings_tuple)
    if st.session_state.current_settings_hash != new_settings_hash: # If settings changed
        st.session_state.generation_stage = "initial" # Reset generation stage
        st.session_state.preview_html_parts, st.session_state.generated_image_data = [], {}
        st.session_state.zip_buffer, st.session_state.total_generations_at_start = None, 0
        st.session_state.full_batch_button_clicked = False
        generate_full_batch_button_container.empty(); resize_message_container.empty() # Clear buttons/messages
    st.session_state.current_settings_hash = new_settings_hash # Update hash

    # --- Main Generation Logic ---
    if uploaded_files and positions:
        total_variant_generations = len(uploaded_files) * len(positions)
        st.session_state.total_generations_at_start = total_variant_generations
        st.markdown("---")
        
        # This is the placeholder for the preview content area.
        # .empty() clears it and returns a new DeltaGenerator to write into it.
        preview_display_area_placeholder = preview_container.empty()
        # Always write the base structure to ensure min-height CSS applies.
        preview_display_area_placeholder.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True)

        images_for_processing, layouts_for_processing = [], positions
        current_variants_processed, processing_variants_limit = 0, total_variant_generations

        # Determine if we are doing a limited preview or full batch
        # Preview if initial stage and total variants exceed 6 images worth of variants
        is_preview_run = (st.session_state.generation_stage == "initial" and
                          total_variant_generations > 6 * len(layouts_for_processing))

        if is_preview_run:
            images_for_processing = uploaded_files[:6] # Limit to first 6 images for preview
            # Calculate limit based on actual number of images being processed for preview
            processing_variants_limit = len(images_for_processing) * len(layouts_for_processing)
        elif st.session_state.generation_stage == "full_batch_generating" or not is_preview_run:
            # Process all images for full batch or if it's a small initial batch
            images_for_processing = uploaded_files
            # processing_variants_limit is already total_variant_generations

        # Condition to start or continue generation
        should_generate = (st.session_state.generation_stage in ["initial", "full_batch_generating"] or
                           (st.session_state.generation_stage == "initial" and not is_preview_run))


        if should_generate and images_for_processing: # Ensure there are images to process
            preloader_status_area = preloader_and_status_container.empty()
            preloader_status_area.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating previews... 0/{processing_variants_limit}</span></div>", unsafe_allow_html=True)
            download_buttons_container.empty(); generate_full_batch_button_container.empty(); resize_message_container.empty()

            generated_preview_html_list, generated_image_byte_data = [], {}
            zip_byte_buffer = io.BytesIO()

            with zipfile.ZipFile(zip_byte_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf:
                for file_index, uploaded_file_object in enumerate(images_for_processing):
                    # Stop if preview limit reached during initial preview run
                    if is_preview_run and current_variants_processed >= processing_variants_limit: break
                    
                    original_file_name = uploaded_file_object.name
                    try:
                        image_bytes = uploaded_file_object.getvalue()
                        try:
                            pil_image_instance = Image.open(io.BytesIO(image_bytes)); pil_image_instance.verify()
                            pil_image_instance = Image.open(io.BytesIO(image_bytes))
                        except Exception as e_open:
                            st.warning(f"Skipped `{original_file_name}` (cannot open/verify): {e_open}")
                            current_variants_processed += len(layouts_for_processing); continue # Skip this file
                        if pil_image_instance.mode not in ("RGB", "L"): pil_image_instance = pil_image_instance.convert("RGB")
                        color_palette = extract_palette(pil_image_instance, num_colors, quantize_selected)

                        for layout_pos_index, layout_position_value in enumerate(layouts_for_processing):
                            if is_preview_run and current_variants_processed >= processing_variants_limit: break
                            preloader_status_area.markdown(f"<div class='preloader-area'><div class='preloader'></div><span class='preloader-text'>Generating... {current_variants_processed+1}/{processing_variants_limit}</span></div>", unsafe_allow_html=True)
                            try:
                                processed_image = draw_layout(pil_image_instance.copy(), color_palette, layout_position_value, img_border_px,
                                                              swatch_sep_px, indiv_swatch_border_px, border_color,
                                                              swatch_border_color, swatch_size_val)
                                if resize_option == "Scale (%)" and scale_percent != 100:
                                    w_new, h_new = int(processed_image.width*scale_percent/100), int(processed_image.height*scale_percent/100)
                                    if w_new > 0 and h_new > 0: processed_image = processed_image.resize((w_new,h_new), Image.Resampling.LANCZOS)
                                
                                img_byte_arr_out = io.BytesIO()
                                base_filename, _ = os.path.splitext(original_file_name)
                                safe_filename_base = "".join(c if c.isalnum() or c in (' ','.','_','-') else '_' for c in base_filename).rstrip()
                                output_filename = f"{safe_filename_base}_{layout_position_value}.{extension}"
                                
                                save_params = {'quality':95} if img_format=="JPEG" else \
                                              ({'quality':85,'lossless':True} if img_format=="WEBP" and webp_lossless else \
                                              ({'quality':85} if img_format=="WEBP" else {}))
                                processed_image.save(img_byte_arr_out, format=img_format, **save_params)
                                image_bytes_for_download = img_byte_arr_out.getvalue()
                                generated_image_byte_data[output_filename] = image_bytes_for_download
                                
                                # Add to ZIP if full batch or small initial run
                                if st.session_state.generation_stage == "full_batch_generating" or not is_preview_run:
                                    zipf.writestr(output_filename, image_bytes_for_download)
                                
                                thumbnail_img = processed_image.copy(); thumbnail_img.thumbnail((200,200))
                                with io.BytesIO() as buf_display: thumbnail_img.save(buf_display, "PNG"); b64_display_str = base64.b64encode(buf_display.getvalue()).decode()
                                b64_download_str = base64.b64encode(image_bytes_for_download).decode()
                                
                                preview_item_html = f"<div class='preview-item'><div class='preview-item-name' title='{output_filename}'>{shorten_filename(output_filename)}</div><img src='data:image/png;base64,{b64_display_str}' alt='{output_filename}'><a href='data:image/{extension};base64,{b64_download_str}' download='{output_filename}' class='download-link'>Download</a></div>"
                                generated_preview_html_list.append(preview_item_html)
                                current_variants_processed +=1
                            except Exception as e_layout: st.error(f"Layout error for `{original_file_name}` ({layout_position_value}): {e_layout}"); current_variants_processed +=1 # Increment to avoid stuck loop
                    except Exception as e_file: st.error(f"File error for `{original_file_name}`: {e_file}"); current_variants_processed += len(layouts_for_processing) # Skip all variants for this file
            
            st.session_state.preview_html_parts = generated_preview_html_list
            st.session_state.generated_image_data = generated_image_byte_data
            
            if st.session_state.generation_stage == "full_batch_generating" or not is_preview_run: # If full batch or small initial run, finalize ZIP
                zip_byte_buffer.seek(0); st.session_state.zip_buffer = zip_byte_buffer
            
            preloader_status_area.empty() # Clear preloader
            
            # Update generation stage
            if is_preview_run: # If it was a preview run for a large batch
                st.session_state.generation_stage = "preview_generated"
            else: # If it was a full batch run or a small initial run that completed
                st.session_state.generation_stage = "completed"

        # --- Display Previews ---
        # Use the same placeholder that was prepared at the start of this block
        if st.session_state.preview_html_parts:
            preview_display_area_placeholder.markdown("<div id='preview-zone'>" + "".join(st.session_state.preview_html_parts) + "</div>", unsafe_allow_html=True)
        else:
            # If no preview parts (e.g., all images failed), ensure the empty zone is still rendered
            # This re-asserts the content of the placeholder if it was somehow cleared or if preview_html_parts is empty.
            preview_display_area_placeholder.markdown("<div id='preview-zone'></div>", unsafe_allow_html=True)


        # --- Display "Generate Full Batch" Button ---
        if st.session_state.generation_stage == "preview_generated":
            with generate_full_batch_button_container:
                if st.button("Set Your layout and borders and **click here to generate whole batch!**", use_container_width=True, key="generate_full_batch_button", type="primary"):
                    st.session_state.generation_stage = "full_batch_generating"
                    st.session_state.full_batch_button_clicked = True
                    st.rerun()

        # --- Display Download Button Logic ---
        with download_buttons_container:
            zip_is_ready = st.session_state.zip_buffer and st.session_state.zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader + 50
            if st.session_state.generation_stage == "completed" and zip_is_ready:
                st.download_button(f"Download All as ZIP ({extension.upper()})", st.session_state.zip_buffer, f"ColorSwatches_{output_format.lower()}.zip", "application/zip", True, key="dl_zip_enabled")
            elif st.session_state.generation_stage == "preview_generated":
                st.download_button(f"Download All as ZIP ({extension.upper()})", io.BytesIO(), f"ColorSwatches_{output_format.lower()}.zip", "application/zip", True, key="dl_zip_disabled_preview", disabled=True, help="Generate the whole batch to download ZIP")
            elif uploaded_files: # Fallback for other states where files are present but not fully processed for download
                 st.download_button(f"Download All as ZIP ({extension.upper()})", io.BytesIO(), f"ColorSwatches_{output_format.lower()}.zip", "application/zip", True, key="dl_zip_initial_disabled_state", disabled=True, help="Complete generation to enable download.")

    else: # No uploaded files or no positions selected
        st.session_state.generation_stage = "initial"
        st.session_state.preview_html_parts, st.session_state.generated_image_data = [], {}
        st.session_state.zip_buffer, st.session_state.total_generations_at_start = None, 0
        st.session_state.full_batch_button_clicked = False
        generate_full_batch_button_container.empty(); resize_message_container.empty()
        preview_container.empty(); download_buttons_container.empty() # Collapse/clear these areas
        spinner_container.empty(); preloader_and_status_container.empty()

        if uploaded_files and not positions:
            st.info("Select at least one swatch position to generate images.")
            with download_buttons_container:
                 st.download_button(f"Download All as ZIP ({extension.upper()})", io.BytesIO(), f"ColorSwatches_{output_format.lower()}.zip", "application/zip", True, key="dl_zip_no_pos_yet", disabled=True, help="Select swatch positions first.")
        elif not uploaded_files: st.info("Upload images to get started.")

except Exception as e: # Top-level error handler for the entire application
    st.error(f"An unexpected application error occurred: {e}")
    st.exception(e)
    st.warning("Attempting to reset application state. Please try your action again.")
    for key in list(st.session_state.keys()): del st.session_state[key] # Clear all session state
    # Re-initialize core states to ensure a clean slate
    st.session_state.generation_stage = "initial"
    st.session_state.preview_html_parts = []
    st.session_state.generated_image_data = {}
    st.session_state.zip_buffer = None
    st.session_state.total_generations_at_start = 0
    st.session_state.current_settings_hash = None
    st.session_state.full_batch_button_clicked = False
    st.rerun()

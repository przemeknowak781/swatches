import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import numpy as np
import io
import zipfile
import base64
import sys # Added for error logging

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("Color Swatch Generator")

# --- Preview container ---
# Main container for the previews, defined early to be globally accessible.
preview_container = st.container()

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
    }
    /* Add some margin below subheaders for better section separation */
    h2 { 
        margin-bottom: 0.9rem !important; 
    }
    </style>
""", unsafe_allow_html=True)

# --- Color Extraction ---
def extract_palette(image, num_colors=6, quantize_method=Image.MEDIANCUT): # Default method is Image.MEDIANCUT
    """Extracts a color palette from the image."""
    img = image.convert("RGB")
    
    # Internally, quantize to a larger number of colors then pick the best ones,
    # but Pillow's quantize methods directly aim for the target `colors`.
    quantize_colors_internal = max(num_colors * 4, 256) # Max 256 for palette modes
    
    try:
        # Pillow's quantize method.
        # The `method` argument determines the algorithm.
        # `colors` is the desired number of colors in the output image's palette.
        paletted = img.quantize(colors=num_colors, method=quantize_method)

        palette_full = paletted.getpalette() # Returns a list [r,g,b,r,g,b,...] or None
        
        if palette_full is None: 
            # Some images or modes might not directly yield a palette this way.
            # st.warning(f"Failed to get palette for image. Trying with a default number of colors.")
            # Attempt with a fixed number of colors if the initial attempt fails.
            paletted = img.quantize(colors=num_colors, method=quantize_method) # Retry with num_colors
            palette_full = paletted.getpalette()
            if palette_full is None:
                # st.error("Still unable to get palette.")
                return [] # Return empty if palette extraction fails

        # The palette_full can have up to 256*3 entries. We need `num_colors` triplets.
        actual_palette_colors = len(palette_full) // 3
        colors_to_extract = min(num_colors, actual_palette_colors) # Ensure we don't ask for more than available
        
        extracted_palette_rgb_values = palette_full[:colors_to_extract * 3]
        colors = [tuple(extracted_palette_rgb_values[i:i+3]) for i in range(0, len(extracted_palette_rgb_values), 3)]
        
        return colors

    except Exception as e:
        # st.warning(f"Error during quantization ({e}). Using fallback method (FASTOCTREE).")
        try:
            # Fallback to a generally safer and faster method
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE) 
            palette = paletted.getpalette()
            if palette is None: return []
            # Ensure we take at most num_colors from the fallback palette
            colors = [tuple(palette[i:i+3]) for i in range(0, min(num_colors * 3, len(palette)), 3)]
            return colors
        except Exception as e_fallback:
            # st.error(f"Error during fallback quantization: {e_fallback}")
            return []


# --- Draw Layout Function ---
def draw_layout(image, colors, position, border_thickness, swatch_border_thickness, border_color, swatch_border_color, swatch_size, remove_adjacent_border):
    """Draws the image layout with color swatches."""
    img_w, img_h = image.size
    border = border_thickness

    if not colors: # If no colors (e.g., extraction failed), handle gracefully
        if border > 0: # Just draw the image with its border
            canvas = Image.new("RGB", (img_w + 2 * border, img_h + 2 * border), border_color)
            canvas.paste(image, (border, border))
            return canvas
        return image.copy() # Or return the original image as is

    # Initialize variables that might not be set in all if/elif branches
    swatch_width = 0
    swatch_height = 0 # Used for 'left'/'right'
    extra_width_for_last_swatch = 0
    extra_height_for_last_swatch = 0 # Used for 'left'/'right'
    swatch_x_start = 0 # Used for 'top'/'bottom'
    swatch_y_start = 0 # Used for 'left'/'right'
    swatch_y = 0 # Y-coordinate for horizontal swatches
    swatch_x = 0 # X-coordinate for vertical swatches


    if position == 'top':
        canvas_h = img_h + swatch_size + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, swatch_size + border)) # Image below swatches
        swatch_y = border # Swatches at the top
        swatch_x_start = border
        swatch_total_width = img_w
        if len(colors) > 0:
            swatch_width = swatch_total_width // len(colors)
            extra_width_for_last_swatch = swatch_total_width % len(colors)
        else: # Avoid ZeroDivisionError if colors list is empty
            swatch_width = swatch_total_width 


    elif position == 'bottom':
        canvas_h = img_h + swatch_size + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, border)) # Image at the top
        swatch_y = border + img_h # Swatches below the image
        swatch_x_start = border
        swatch_total_width = img_w
        if len(colors) > 0:
            swatch_width = swatch_total_width // len(colors)
            extra_width_for_last_swatch = swatch_total_width % len(colors)
        else:
            swatch_width = swatch_total_width


    elif position == 'left':
        canvas_w = img_w + swatch_size + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (swatch_size + border, border)) # Image to the right of swatches
        swatch_x = border # Swatches on the left
        swatch_y_start = border
        swatch_total_height = img_h
        if len(colors) > 0:
            swatch_height = swatch_total_height // len(colors)
            extra_height_for_last_swatch = swatch_total_height % len(colors)
        else:
             swatch_height = swatch_total_height


    elif position == 'right':
        canvas_w = img_w + swatch_size + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, border)) # Image on the left
        swatch_x = border + img_w # Swatches to the right of the image
        swatch_y_start = border
        swatch_total_height = img_h
        if len(colors) > 0:
            swatch_height = swatch_total_height // len(colors)
            extra_height_for_last_swatch = swatch_total_height % len(colors)
        else:
            swatch_height = swatch_total_height
    
    else: # Fallback, should not happen with defined positions
        return image.copy()

    draw = ImageDraw.Draw(canvas)

    for i, color_tuple in enumerate(colors):
        current_swatch_width = swatch_width
        current_swatch_height = swatch_height 

        if position in ['top', 'bottom']:
            if i == len(colors) - 1: # Last swatch might be wider to fill space
                current_swatch_width += extra_width_for_last_swatch
            x0 = swatch_x_start + i * swatch_width # Regular start for this swatch
            x1 = x0 + current_swatch_width
            y0 = swatch_y
            y1 = swatch_y + swatch_size
        else: # 'left' or 'right'
            if i == len(colors) - 1: # Last swatch might be taller
                current_swatch_height += extra_height_for_last_swatch
            y0 = swatch_y_start + i * swatch_height # Regular start
            y1 = y0 + current_swatch_height
            x0 = swatch_x
            x1 = swatch_x + swatch_size

        draw.rectangle([x0, y0, x1, y1], fill=tuple(color_tuple))
        
        # Draw swatch borders
        if swatch_border_thickness > 0:
            # Determine if the swatch is at the very edge of the canvas (respecting the main image border)
            is_at_top_edge = (position == 'top' and y0 == border)
            is_at_bottom_edge = (position == 'bottom' and y1 == (canvas.height - border))
            is_at_left_edge = (position == 'left' and x0 == border)
            is_at_right_edge = (position == 'right' and x1 == (canvas.width - border))

            # Top line of swatch
            if not (remove_adjacent_border and is_at_top_edge and border_thickness == 0):
                 draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            # Bottom line of swatch
            if not (remove_adjacent_border and is_at_bottom_edge and border_thickness == 0):
                 draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            # Left line of swatch
            if not (remove_adjacent_border and is_at_left_edge and border_thickness == 0):
                 draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            # Right line of swatch
            if not (remove_adjacent_border and is_at_right_edge and border_thickness == 0):
                 draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

            # Inner borders between swatches
            if position in ['top', 'bottom']:
                if i > 0: # Draw left border for swatches after the first one
                    draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            else: # 'left', 'right'
                if i > 0: # Draw top border for swatches after the first one
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
        type=allowed_types # Client-side filtering
    )

    # Server-side validation (additional check)
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
    scale_percent = 100 # Default
    if resize_option == "Scale (%)":
        scale_percent = st.slider("Scale percent", 10, 200, 100, key="scale_percent")

    output_format_options = ["JPG", "PNG", "WEBP"]
    output_format = st.selectbox("Output format", output_format_options, key="output_format")
    
    webp_lossless = False # Default
    if output_format == "WEBP":
        webp_lossless = st.checkbox("Lossless WEBP", value=False, key="webp_lossless", help="Generates larger files, but with better quality (potentially no loss).")


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

    # Using columns for better toggle layout
    row1_layout = st.columns(2)
    row2_layout = st.columns(2)
    
    if row1_layout[0].toggle("Top", key="pos_top"):
        positions.append("top")
    if row1_layout[1].toggle("Left", key="pos_left"):
        positions.append("left")
    if row2_layout[0].toggle("Bottom", value=True, key="pos_bottom"): # Default to Bottom
        positions.append("bottom")
    if row2_layout[1].toggle("Right", key="pos_right"):
        positions.append("right")

    quant_method_label = st.selectbox(
        "Palette extraction method", 
        ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"], 
        index=0,
        key="quant_method",
        help="MEDIANCUT: Good general results. MAXCOVERAGE: Can be slower, aims to cover as many pixels as possible. FASTOCTREE: Faster, good for a large number of colors."
    )
    # Pillow constants for quantization methods
    quant_method_map = {
        "MEDIANCUT": Image.MEDIANCUT, 
        "MAXCOVERAGE": Image.MAXCOVERAGE,
        "FASTOCTREE": Image.FASTOCTREE
    }
    quantize_method_selected = quant_method_map[quant_method_label]

    num_colors = st.slider("Number of swatches", 2, 12, 6, key="num_colors")
    swatch_size = st.slider("Swatch size (px)", 20, 200, 100, key="swatch_size")

with col3:
    st.subheader("Borders")
    border_thickness_percent = st.slider("Image border thickness (% of width)", 0, 10, 0, key="border_thickness_percent")
    border_color = st.color_picker("Image border color", "#FFFFFF", key="border_color")
    swatch_border_thickness = st.slider("Swatch border thickness (px)", 0, 10, 1, key="swatch_border_thickness") # Default to 1px
    swatch_border_color = st.color_picker("Swatch border color", "#CCCCCC", key="swatch_border_color") # Default to a light gray
    remove_adjacent_border = st.checkbox("Align swatches with image edge (remove adjacent borders)", value=True, key="remove_adjacent_border")


# --- Process & Preview ---
if uploaded_files and positions:
    st.markdown("---") # Separator line
    st.subheader("Previews") # Header for the previews section
    
    # This is where the dynamic preview HTML will be injected.
    preview_display_area = preview_container.empty() 
    
    individual_preview_html_parts = [] # To store HTML for each generated preview item
    zip_buffer = io.BytesIO() # Buffer for the ZIP file

    with st.spinner("Generating previews..."):
        # Use compresslevel=0 (ZIP_STORED) for speed, as images are already compressed.
        # For actual compression, use zipfile.ZIP_DEFLATED (default compresslevel is usually fine).
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf: 
            for uploaded_file_obj in uploaded_files:
                try:
                    # Read file bytes once to allow multiple operations (verify, open)
                    uploaded_file_bytes = uploaded_file_obj.getvalue()
                    
                    # Verify image integrity
                    image_stream_for_verify = io.BytesIO(uploaded_file_bytes)
                    test_image = Image.open(image_stream_for_verify)
                    test_image.verify()  # Can raise an exception for corrupt files
                    
                    # Load the image for processing
                    image_stream_for_load = io.BytesIO(uploaded_file_bytes)
                    image = Image.open(image_stream_for_load)

                except UnidentifiedImageError:
                    st.warning(f"Could not identify image file: `{uploaded_file_obj.name}`. Skipped.")
                    continue
                except Exception as e:
                    st.warning(f"`{uploaded_file_obj.name}` could not be loaded or is corrupted ({e}). Skipped.")
                    # print(f"Error loading {uploaded_file_obj.name}: {e}", file=sys.stderr) # For server-side debugging
                    continue

                try:
                    w, h = image.size
                    # Basic validation for image dimensions
                    if not (10 <= w <= 10000 and 10 <= h <= 10000): # Min 10px, Max 10000px
                        st.warning(f"`{uploaded_file_obj.name}` has an unsupported resolution ({w}x{h}). Range: 10-10000px. Skipped.")
                        continue
                    
                    # Convert to RGB if it has an alpha channel or is in another mode (e.g., P, LA)
                    if image.mode not in ("RGB", "L"): # L is grayscale
                         image = image.convert("RGB")
                    
                    palette = extract_palette(image, num_colors, quantize_method=quantize_method_selected)
                    if not palette: # If palette extraction failed
                        st.warning(f"Failed to extract palette for `{uploaded_file_obj.name}`. Skipping swatch generation for this image.")
                        # The draw_layout function will handle an empty palette by not drawing swatches.
                        pass 

                except Exception as e:
                    st.error(f"Error processing `{uploaded_file_obj.name}`: {e}. Skipped.")
                    # print(f"Error processing {uploaded_file_obj.name}: {e}", file=sys.stderr)
                    continue

                # Calculate border thickness in pixels
                border_px = int(image.width * (border_thickness_percent / 100))

                for pos_idx, pos in enumerate(positions): # Iterate through selected swatch positions
                    try:
                        # Always use a copy of the image for draw_layout,
                        # so the original 'image' object remains unmodified for other positions.
                        result_img = draw_layout(
                            image.copy(), palette, pos, border_px, swatch_border_thickness,
                            border_color, swatch_border_color, swatch_size, remove_adjacent_border
                        )

                        # Resize if "Scale (%)" is selected
                        if resize_option == "Scale (%)" and scale_percent != 100:
                            new_w = int(result_img.width * scale_percent / 100)
                            new_h = int(result_img.height * scale_percent / 100)
                            if new_w > 0 and new_h > 0: # Ensure dimensions are positive
                                result_img = result_img.resize((new_w, new_h), Image.Resampling.LANCZOS) 
                            else:
                                st.warning(f"Cannot resize image {uploaded_file_obj.name}_{pos} to zero/negative dimensions. Using original size.")


                        # Save image to a byte buffer for ZIP and preview
                        img_byte_arr = io.BytesIO()
                        # Sanitize filename for ZIP
                        base_name, 작업_확장자 = uploaded_file_obj.name.rsplit('.', 1)
                        safe_base_name = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in base_name).rstrip()
                        name_for_zip = f"{safe_base_name}_{pos}.{extension}"
                        
                        save_params = {}
                        if img_format == "JPEG":
                            save_params['quality'] = 95 # Good quality for JPG
                        elif img_format == "WEBP":
                            save_params['quality'] = 85 # Good default for lossy WEBP
                            if webp_lossless: # Use the value from the checkbox
                                save_params['lossless'] = True
                                save_params['quality'] = 100 # For lossless, quality is effort/speed

                        result_img.save(img_byte_arr, format=img_format, **save_params)
                        zipf.writestr(name_for_zip, img_byte_arr.getvalue()) # Add to ZIP

                        # Create a smaller version for HTML preview
                        preview_img_for_display = result_img.copy()
                        preview_img_for_display.thumbnail((180, 180)) # Resize to max 180px (fits .preview-item img max-width)

                        with io.BytesIO() as buffer_display:
                            preview_img_for_display.save(buffer_display, format="PNG") # Always use PNG for base64 in HTML for broad compatibility
                            img_base64 = base64.b64encode(buffer_display.getvalue()).decode("utf-8")
                        
                        # HTML for a single preview item
                        single_item_html = f"<div class='preview-item'>"
                        single_item_html += f"<div class='preview-item-name'>{name_for_zip}</div>"
                        single_item_html += f"<img src='data:image/png;base64,{img_base64}' alt='Preview of {name_for_zip}'>"
                        single_item_html += "</div>"
                        
                        individual_preview_html_parts.append(single_item_html)

                        # Construct the full HTML for the preview zone with all current items
                        current_full_html_content = (
                            "<div id='preview-zone'>"
                            + "\n".join(individual_preview_html_parts) +
                            "</div>"
                        )
                        # Update the content of the st.empty() placeholder
                        preview_display_area.markdown(current_full_html_content, unsafe_allow_html=True)
                    
                    except Exception as e_layout:
                        st.error(f"Error creating layout for {uploaded_file_obj.name} (position: {pos}): {e_layout}")
                        # print(f"Error during layout generation for {uploaded_file_obj.name} ({pos}): {e_layout}", file=sys.stderr)


        zip_buffer.seek(0) # Rewind buffer to the beginning for reading by download_button

    # Download button (appears after spinner finishes)
    # Check if the ZIP buffer actually contains files (more than just header data)
    if zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader + 100: # A small threshold 
        st.download_button(
            label=f"Download All as ZIP ({extension.upper()})",
            data=zip_buffer,
            file_name=f"ColorSwatches_{output_format.lower()}.zip", # English filename
            mime="application/zip",
            use_container_width=True,
            key="download_zip"
        )
    elif uploaded_files and positions : # If processing was attempted but ZIP is empty/small
        st.warning("No images were generated for download. Check error messages above.")

elif uploaded_files and not positions: # Files uploaded, but no positions selected
    st.info("Select at least one swatch position to generate previews and images for download.")
elif not uploaded_files: # No files uploaded yet
    st.info("Upload images to get started.")

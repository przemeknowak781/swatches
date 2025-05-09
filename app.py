import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import numpy as np
import io
import zipfile
import base64
import sys # Dodane do logowania błędów

# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("🎨 Generator Próbek Kolorów")

# --- Preview container ---
# Główny kontener na podglądy, zdefiniowany na początku, aby był dostępny globalnie w skrypcie.
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
    /* Dodatkowe style dla strefy podglądu, jeśli potrzebne */
    #preview-zone {
        display: flex;
        flex-wrap: nowrap; /* Zapobiega zawijaniu, umożliwia przewijanie */
        overflow-x: auto; /* Umożliwia poziome przewijanie */
        gap: 30px;        /* Odstęp między elementami podglądu */
        padding: 20px;    /* Wewnętrzny margines strefy podglądu */
        border-radius: 8px; /* Zaokrąglone rogi dla estetyki */
        /* background-color: #f9f9f9; /* Lekkie tło dla strefy podglądu */
    }
    .preview-item {
        flex: 0 0 auto; /* Elementy nie będą się rozciągać ani kurczyć */
        text-align: center;
        width: 200px; /* Stała szerokość dla każdego elementu podglądu */
        box-shadow: 0 4px 12px rgba(0,0,0,0.15); /* Subtelny cień */
        padding: 10px; /* Wewnętrzny margines dla elementu */
        border-radius: 8px; /* Zaokrąglone rogi */
        background: #ffffff; /* Białe tło dla każdego elementu */
        border: 1px solid #e0e0e0; /* Delikatna ramka */
    }
    .preview-item img {
        width: 100%; /* Obrazek zajmuje całą dostępną szerokość w kontenerze .preview-item */
        max-width: 180px; /* Maksymalna szerokość obrazka, aby zostawić trochę paddingu */
        height: auto;     /* Zachowaj proporcje obrazka */
        border-radius: 4px; /* Lekko zaokrąglone rogi obrazka */
        margin-bottom: 8px; /* Odstęp pod obrazkiem */
    }
    .preview-item-name {
        font-size: 12px;
        margin-bottom: 5px;
        color: #333; /* Ciemniejszy kolor tekstu dla lepszej czytelności */
        word-break: break-all; /* Łamanie długich nazw plików */
    }
    </style>
""", unsafe_allow_html=True)

# --- Color Extraction ---
def extract_palette(image, num_colors=6, quantize_method=Image.MEDIANCUT): # domyślna metoda to Image.MEDIANCUT
    """Ekstrahuje paletę kolorów z obrazu."""
    img = image.convert("RGB")
    
    quantize_colors_internal = max(num_colors * 4, 16) 
    
    try:
        # Pillow >= 9.1.0 używa kmeans jako argumentu, a nie w metodzie.
        # Starsze wersje mogą tego nie obsługiwać lub obsługiwać inaczej.
        # Sprawdźmy wersję Pillow, aby dostosować wywołanie.
        pillow_version = Image.__version__
        major_version, minor_version, _ = map(int, pillow_version.split('.'))

        if major_version >= 9 and minor_version >= 1:
             # Dla Pillow 9.1.0+ przekazujemy `kmeans` jako argument, jeśli chcemy użyć k-średnich
             # Jednak standardowe metody kwantyzacji (MEDIANCUT, MAXCOVERAGE, FASTOCTREE) nie używają `kmeans` w ten sposób.
             # Argument `kmeans` jest bardziej dla metody `Image.Quantize. ตุ๊กตา` (jeśli istnieje) lub specyficznych zastosowań.
             # Dla standardowych metod, po prostu podajemy `colors` i `method`.
            paletted = img.quantize(colors=quantize_colors_internal, method=quantize_method)
        else:
            # Dla starszych wersji Pillow
            paletted = img.quantize(colors=quantize_colors_internal, method=quantize_method)

        palette_full = paletted.getpalette()
        
        if palette_full is None: # Niektóre obrazy mogą nie zwracać palety
            # st.warning(f"Nie udało się uzyskać palety dla obrazu. Próba z mniejszą liczbą kolorów.")
            paletted = img.quantize(colors=num_colors, method=quantize_method)
            palette_full = paletted.getpalette()
            if palette_full is None:
                # st.error("Nadal nie można uzyskać palety.")
                return []


        actual_palette_colors = len(palette_full) // 3
        colors_to_extract = min(num_colors, actual_palette_colors)
        
        palette = palette_full[:colors_to_extract * 3]
        colors = [tuple(palette[i:i+3]) for i in range(0, len(palette), 3)]
        
        return colors

    except Exception as e:
        # st.warning(f"Błąd podczas kwantyzacji ({e}). Używam prostszej metody (FASTOCTREE).")
        try:
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE) 
            palette = paletted.getpalette()
            if palette is None: return []
            colors = [tuple(palette[i:i+3]) for i in range(0, min(num_colors * 3, len(palette)), 3)]
            return colors
        except Exception as e_fallback:
            # st.error(f"Błąd podczas kwantyzacji zapasowej: {e_fallback}")
            return []


# --- Draw Layout Function ---
def draw_layout(image, colors, position, border_thickness, swatch_border_thickness, border_color, swatch_border_color, swatch_size, remove_adjacent_border):
    """Rysuje układ obrazu z próbkami kolorów."""
    img_w, img_h = image.size
    border = border_thickness

    if not colors: 
        if border > 0:
            canvas = Image.new("RGB", (img_w + 2 * border, img_h + 2 * border), border_color)
            canvas.paste(image, (border, border))
            return canvas
        return image.copy()

    # Inicjalizacja zmiennych, które mogą nie być ustawione we wszystkich gałęziach if/elif
    swatch_width = 0
    swatch_height = 0
    extra_width_for_last_swatch = 0
    extra_height_for_last_swatch = 0
    swatch_x_start = 0
    swatch_y_start = 0


    if position == 'top':
        canvas_h = img_h + swatch_size + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, swatch_size + border))
        swatch_y = border
        swatch_x_start = border
        swatch_total_width = img_w
        if len(colors) > 0:
            swatch_width = swatch_total_width // len(colors)
            extra_width_for_last_swatch = swatch_total_width % len(colors)
        else: # Uniknięcie ZeroDivisionError
            swatch_width = swatch_total_width 


    elif position == 'bottom':
        canvas_h = img_h + swatch_size + 2 * border
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
        canvas_w = img_w + swatch_size + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (swatch_size + border, border))
        swatch_x = border
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

    for i, color in enumerate(colors):
        current_swatch_width = swatch_width
        current_swatch_height = swatch_height # Inicjalizacja dla obu przypadków

        if position in ['top', 'bottom']:
            if i == len(colors) - 1: 
                current_swatch_width += extra_width_for_last_swatch
            x0 = swatch_x_start + i * swatch_width
            x1 = x0 + current_swatch_width
            y0 = swatch_y
            y1 = swatch_y + swatch_size
        else: # left or right
            current_swatch_height = swatch_height # Upewnij się, że jest zdefiniowane
            if i == len(colors) - 1: 
                current_swatch_height += extra_height_for_last_swatch
            y0 = swatch_y_start + i * swatch_height
            y1 = y0 + current_swatch_height
            x0 = swatch_x
            x1 = swatch_x + swatch_size

        draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
        
        if swatch_border_thickness > 0:
            adj_x0, adj_y0, adj_x1, adj_y1 = x0, y0, x1, y1

            # Górna linia
            if not (remove_adjacent_border and position == 'top' and border_thickness == 0 and y0 == border):
                 draw.line([(adj_x0, adj_y0), (adj_x1, adj_y0)], fill=swatch_border_color, width=swatch_border_thickness)
            # Dolna linia
            if not (remove_adjacent_border and position == 'bottom' and border_thickness == 0 and y1 == canvas.height - border):
                 draw.line([(adj_x0, adj_y1), (adj_x1, adj_y1)], fill=swatch_border_color, width=swatch_border_thickness)
            # Lewa linia
            if not (remove_adjacent_border and position == 'left' and border_thickness == 0 and x0 == border):
                 draw.line([(adj_x0, adj_y0), (adj_x0, adj_y1)], fill=swatch_border_color, width=swatch_border_thickness)
            # Prawa linia
            if not (remove_adjacent_border and position == 'right' and border_thickness == 0 and x1 == canvas.width - border):
                 draw.line([(adj_x1, adj_y0), (adj_x1, adj_y1)], fill=swatch_border_color, width=swatch_border_thickness)

            # Wewnętrzne linie między próbkami
            if position in ['top', 'bottom']:
                if i > 0: 
                    draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            else: # left, right
                if i > 0: 
                    draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
    return canvas

# --- Input Columns ---
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("🖼️ Prześlij Obrazy")
    allowed_types = ["jpg", "jpeg", "png", "webp", "jfif", "bmp", "tiff", "tif"]
    uploaded_files = st.file_uploader(
        "Wybierz obrazy",
        accept_multiple_files=True,
        type=allowed_types 
    )

    valid_files_after_upload = []
    if uploaded_files:
        valid_extensions_tuple = tuple(f".{ext}" for ext in allowed_types)
        for file_idx, file in enumerate(uploaded_files):
            # Każdy plik potrzebuje unikalnego klucza, jeśli będziemy go modyfikować lub resetować
            # Na razie nie jest to konieczne, ale warto pamiętać
            if not file.name.lower().endswith(valid_extensions_tuple):
                st.warning(f"⚠️ `{file.name}` ma nieobsługiwane rozszerzenie. Pominięto.")
            else:
                valid_files_after_upload.append(file)
        uploaded_files = valid_files_after_upload

    st.subheader("⚙️ Opcje Pobierania")
    resize_option = st.radio("Metoda zmiany rozmiaru", ["Oryginalny rozmiar", "Skaluj (%)"], index=0, key="resize_option")
    scale_percent = 100
    if resize_option == "Skaluj (%)":
        scale_percent = st.slider("Procent skalowania", 10, 200, 100, key="scale_percent")

    output_format_options = ["JPG", "PNG", "WEBP"]
    output_format = st.selectbox("Format wyjściowy", output_format_options, key="output_format")
    
    # Opcje specyficzne dla formatu WEBP
    webp_lossless = False
    if output_format == "WEBP":
        webp_lossless = st.checkbox("WEBP bezstratny", value=False, key="webp_lossless", help="Generuje większe pliki, ale z lepszą jakością.")


    format_map = {
        "JPG": ("JPEG", "jpg"),
        "PNG": ("PNG", "png"),
        "WEBP": ("WEBP", "webp")
    }
    img_format, extension = format_map[output_format]

with col2:
    st.subheader("🎨 Ustawienia Układu")
    positions = []
    st.write("Pozycja próbek (można wybrać wiele):")

    row1_layout = st.columns(2)
    row2_layout = st.columns(2)
    
    if row1_layout[0].toggle("Góra", key="pos_top"):
        positions.append("top")
    if row1_layout[1].toggle("Lewo", key="pos_left"):
        positions.append("left")
    if row2_layout[0].toggle("Dół", value=True, key="pos_bottom"): 
        positions.append("bottom")
    if row2_layout[1].toggle("Prawo", key="pos_right"):
        positions.append("right")

    quant_method_label = st.selectbox(
        "Metoda ekstrakcji palety", 
        ["MEDIANCUT", "MAXCOVERAGE", "FASTOCTREE"], 
        index=0,
        key="quant_method",
        help="MEDIANCUT: Dobre ogólne wyniki. MAXCOVERAGE: Może być wolniejsza, dąży do pokrycia jak największej liczby pikseli. FASTOCTREE: Szybsza, dobra dla dużej liczby kolorów."
    )
    quant_method_map = {
        "MEDIANCUT": Image.MEDIANCUT, 
        "MAXCOVERAGE": Image.MAXCOVERAGE,
        "FASTOCTREE": Image.FASTOCTREE
    }
    quantize_method_selected = quant_method_map[quant_method_label]

    num_colors = st.slider("Liczba próbek", 2, 12, 6, key="num_colors")
    swatch_size = st.slider("Rozmiar próbki (px)", 20, 200, 100, key="swatch_size")

with col3:
    st.subheader("🖼️ Ramki")
    border_thickness_percent = st.slider("Grubość ramki obrazu (% szerokości)", 0, 10, 0, key="border_thickness_percent")
    border_color = st.color_picker("Kolor ramki obrazu", "#FFFFFF", key="border_color")
    swatch_border_thickness = st.slider("Grubość ramki próbki (px)", 0, 10, 1, key="swatch_border_thickness")
    swatch_border_color = st.color_picker("Kolor ramki próbki", "#CCCCCC", key="swatch_border_color") 
    remove_adjacent_border = st.checkbox("Dopasuj próbki do krawędzi obrazu (usuń przyległe ramki)", value=True, key="remove_adjacent_border")


# --- Process & Preview ---
if uploaded_files and positions:
    st.markdown("---") 
    st.subheader("🖼️ Podglądy")
    
    preview_display_area = preview_container.empty()
    individual_preview_html_parts = []
    zip_buffer = io.BytesIO()

    # Użyj st.session_state do przechowywania stanu webp_lossless, jeśli jest potrzebny wewnątrz pętli
    # (chociaż w tym przypadku jest pobierany bezpośrednio przed pętlą)
    # if 'webp_lossless' not in st.session_state: # Inicjalizacja, jeśli nie istnieje
    #    st.session_state.webp_lossless = False


    with st.spinner("⏳ Generowanie podglądów..."):
        # Używamy compresslevel=0 (ZIP_STORED) dla szybkości, ponieważ obrazy są już skompresowane.
        # Jeśli chcemy kompresji ZIP, użyjmy zipfile.ZIP_DEFLATED i domyślnego compresslevel.
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=0) as zipf: 
            for uploaded_file_obj in uploaded_files:
                try:
                    # Klonowanie UploadedFile, aby uniknąć problemów z wielokrotnym odczytem
                    # To jest ważne, jeśli plik jest modyfikowany lub odczytywany wielokrotnie
                    # Jednak Image.open() powinien obsługiwać strumienie poprawnie.
                    # Dla pewności, można odczytać bajty raz.
                    uploaded_file_bytes = uploaded_file_obj.getvalue()
                    
                    # Sprawdzenie integralności obrazu
                    image_stream_for_verify = io.BytesIO(uploaded_file_bytes)
                    test_image = Image.open(image_stream_for_verify)
                    test_image.verify()  
                    
                    image_stream_for_load = io.BytesIO(uploaded_file_bytes)
                    image = Image.open(image_stream_for_load)

                except UnidentifiedImageError:
                    st.warning(f"⚠️ Nie można zidentyfikować pliku obrazu: `{uploaded_file_obj.name}`. Pominięto.")
                    continue
                except Exception as e:
                    st.warning(f"⚠️ `{uploaded_file_obj.name}` nie mógł zostać załadowany lub jest uszkodzony ({e}). Pominięto.")
                    # print(f"Error loading {uploaded_file_obj.name}: {e}", file=sys.stderr) # Logowanie do konsoli
                    continue

                try:
                    w, h = image.size
                    if not (10 <= w <= 10000 and 10 <= h <= 10000):
                        st.warning(f"⚠️ `{uploaded_file_obj.name}` ma nieobsługiwaną rozdzielczość ({w}x{h}). Zakres: 10-10000px. Pominięto.")
                        continue
                    
                    if image.mode not in ("RGB", "L"): 
                         image = image.convert("RGB")
                    
                    palette = extract_palette(image, num_colors, quantize_method=quantize_method_selected)
                    if not palette: 
                        st.warning(f"⚠️ Nie udało się wyekstrahować palety dla `{uploaded_file_obj.name}`. Pominięto generowanie próbek dla tego obrazu.")
                        pass 

                except Exception as e:
                    st.error(f"⚠️ Błąd przetwarzania `{uploaded_file_obj.name}`: {e}. Pominięto.")
                    # print(f"Error processing {uploaded_file_obj.name}: {e}", file=sys.stderr)
                    continue

                border_px = int(image.width * (border_thickness_percent / 100))

                for pos_idx, pos in enumerate(positions):
                    try:
                        # Zawsze używaj kopii obrazu dla draw_layout, aby oryginał pozostał nietknięty dla innych pozycji
                        result_img = draw_layout(
                            image.copy(), palette, pos, border_px, swatch_border_thickness,
                            border_color, swatch_border_color, swatch_size, remove_adjacent_border
                        )

                        if resize_option == "Skaluj (%)" and scale_percent != 100:
                            new_w = int(result_img.width * scale_percent / 100)
                            new_h = int(result_img.height * scale_percent / 100)
                            if new_w > 0 and new_h > 0:
                                result_img = result_img.resize((new_w, new_h), Image.Resampling.LANCZOS) 
                            else:
                                st.warning(f"Nie można przeskalować obrazu {uploaded_file_obj.name}_{pos} do zerowych/ujemnych wymiarów. Użyto oryginalnych.")


                        img_byte_arr = io.BytesIO()
                        base_name, _ = uploaded_file_obj.name.rsplit('.', 1)
                        safe_base_name = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in base_name).rstrip()
                        name_for_zip = f"{safe_base_name}_{pos}.{extension}"
                        
                        save_params = {}
                        if img_format == "JPEG":
                            save_params['quality'] = 95 
                        elif img_format == "WEBP":
                            save_params['quality'] = 85 # Domyślna jakość dla stratnego WEBP
                            if webp_lossless: # Użyj wartości pobranej wcześniej
                                save_params['lossless'] = True
                                save_params['quality'] = 100 # Dla lossless, quality to wysiłek kompresji

                        result_img.save(img_byte_arr, format=img_format, **save_params)
                        zipf.writestr(name_for_zip, img_byte_arr.getvalue())

                        preview_img_for_display = result_img.copy()
                        preview_img_for_display.thumbnail((180, 180)) # Zmniejsz do max 180px, pasuje do .preview-item img max-width

                        with io.BytesIO() as buffer_display:
                            preview_img_for_display.save(buffer_display, format="PNG") 
                            img_base64 = base64.b64encode(buffer_display.getvalue()).decode("utf-8")
                        
                        single_item_html = f"<div class='preview-item'>"
                        single_item_html += f"<div class='preview-item-name'>{name_for_zip}</div>"
                        single_item_html += f"<img src='data:image/png;base64,{img_base64}' alt='Podgląd {name_for_zip}'>"
                        single_item_html += "</div>"
                        
                        individual_preview_html_parts.append(single_item_html)

                        current_full_html_content = (
                            "<div id='preview-zone'>"
                            + "\n".join(individual_preview_html_parts) +
                            "</div>"
                        )
                        preview_display_area.markdown(current_full_html_content, unsafe_allow_html=True)
                    
                    except Exception as e_layout:
                        st.error(f"Błąd podczas tworzenia układu dla {uploaded_file_obj.name} ({pos}): {e_layout}")
                        # print(f"Error during layout generation for {uploaded_file_obj.name} ({pos}): {e_layout}", file=sys.stderr)


        zip_buffer.seek(0)

    if zip_buffer.getbuffer().nbytes > zipfile.sizeFileHeader: # Sprawdź, czy ZIP zawiera więcej niż tylko nagłówki
        st.download_button(
            label=f"📦 Pobierz wszystko jako ZIP ({extension.upper()})",
            data=zip_buffer,
            file_name=f"PróbkiKolorów_{output_format.lower()}.zip",
            mime="application/zip",
            use_container_width=True,
            key="download_zip"
        )
    elif uploaded_files and positions : 
        st.warning("⚠️ Nie wygenerowano żadnych obrazów do pobrania. Sprawdź komunikaty o błędach powyżej.")

elif uploaded_files and not positions:
    st.info("ℹ️ Wybierz przynajmniej jedną pozycję dla próbek kolorów, aby wygenerować podglądy i obrazy do pobrania.")
elif not uploaded_files:
    st.info("ℹ️ Prześlij obrazy, aby rozpocząć.")


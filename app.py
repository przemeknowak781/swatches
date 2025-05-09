import streamlit as st
from PIL import Image, ImageDraw, UnidentifiedImageError
import numpy as np
import io
import zipfile
import base64

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
def extract_palette(image, num_colors=6, quantize_method=Image.MEDIANCUT):
    """Ekstrahuje paletę kolorów z obrazu."""
    img = image.convert("RGB")
    # Opcjonalne zmniejszenie obrazu dla lepszej wydajności, szczególnie przy dużych obrazach
    # img.thumbnail((500, 500)) # Można dostosować rozmiar
    
    # Użyj kwantyzacji Pillow do zredukowania obrazu do palety
    # Zwiększenie liczby kolorów dla kwantyzacji może dać lepsze wyniki, jeśli num_colors jest małe
    quantize_colors = max(num_colors * 4, 16) # Np. kwantyzuj do większej liczby, a potem wybierz najlepsze
    
    try:
        paletted = img.quantize(colors=quantize_colors, method=quantize_method, kmeans=num_colors)
        palette_full = paletted.getpalette()
        
        # Wybierz 'num_colors' najbardziej dominujących kolorów z wygenerowanej palety
        # (Pillow nie sortuje palety wg dominacji, więc bierzemy pierwsze 'num_colors')
        # Jeśli metoda kwantyzacji zwraca dokładną liczbę kolorów, to jest to prostsze.
        # Dla MEDIANCUT, MAXCOVERAGE, FASTOCTREE, getpalette() zwraca do 256 kolorów (RGB triplets)
        
        # Jeśli paleta jest mniejsza niż oczekiwano, dostosuj
        actual_palette_colors = len(palette_full) // 3
        colors_to_extract = min(num_colors, actual_palette_colors)
        
        palette = palette_full[:colors_to_extract * 3]
        colors = [tuple(palette[i:i+3]) for i in range(0, len(palette), 3)]
        
        # Jeśli mamy mniej kolorów niż `num_colors`, możemy je powielić lub dodać domyślne
        # Na razie zwracamy tyle, ile udało się wyekstrahować
        return colors

    except Exception as e:
        # st.warning(f"Błąd podczas kwantyzacji: {e}. Używam prostszej metody.")
        # W przypadku błędu, można spróbować prostszej metody lub mniejszej liczby kolorów
        try:
            paletted = img.quantize(colors=num_colors, method=Image.FASTOCTREE) # FASTOCTREE jest zwykle bezpieczniejszy
            palette = paletted.getpalette()[:num_colors * 3]
            colors = [tuple(palette[i:i+3]) for i in range(0, len(palette), 3)]
            return colors
        except Exception: # Ostateczny fallback
            # Zwróć np. jeden średni kolor lub pustą listę
            # For simplicity, let's return a single average color if all else fails
            # Or handle it by returning fewer colors than requested.
            # For now, we'll let the original error propagate if the fallback also fails,
            # or return an empty list to signify failure.
            return []


# --- Draw Layout Function ---
def draw_layout(image, colors, position, border_thickness, swatch_border_thickness, border_color, swatch_border_color, swatch_size, remove_adjacent_border):
    """Rysuje układ obrazu z próbkami kolorów."""
    img_w, img_h = image.size
    border = border_thickness

    if not colors: # Jeśli nie ma kolorów (np. błąd ekstrakcji), nie rysuj próbek
        # Zwróć oryginalny obraz z ramką, jeśli jest
        if border > 0:
            canvas = Image.new("RGB", (img_w + 2 * border, img_h + 2 * border), border_color)
            canvas.paste(image, (border, border))
            return canvas
        return image.copy()


    if position == 'top':
        canvas_h = img_h + swatch_size + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, swatch_size + border))
        swatch_y = border
        swatch_x_start = border
        swatch_total_width = img_w
        swatch_width = swatch_total_width // len(colors)
        extra_width_for_last_swatch = swatch_total_width % len(colors)

    elif position == 'bottom':
        canvas_h = img_h + swatch_size + 2 * border
        canvas_w = img_w + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, border))
        swatch_y = border + img_h
        swatch_x_start = border
        swatch_total_width = img_w
        swatch_width = swatch_total_width // len(colors)
        extra_width_for_last_swatch = swatch_total_width % len(colors)

    elif position == 'left':
        canvas_w = img_w + swatch_size + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (swatch_size + border, border))
        swatch_x = border
        swatch_y_start = border
        swatch_total_height = img_h
        swatch_height = swatch_total_height // len(colors)
        extra_height_for_last_swatch = swatch_total_height % len(colors)

    elif position == 'right':
        canvas_w = img_w + swatch_size + 2 * border
        canvas_h = img_h + 2 * border
        canvas = Image.new("RGB", (canvas_w, canvas_h), border_color)
        canvas.paste(image, (border, border))
        swatch_x = border + img_w
        swatch_y_start = border
        swatch_total_height = img_h
        swatch_height = swatch_total_height // len(colors)
        extra_height_for_last_swatch = swatch_total_height % len(colors)
    
    else: # Fallback, should not happen
        return image.copy()

    draw = ImageDraw.Draw(canvas)

    for i, color in enumerate(colors):
        current_swatch_width = swatch_width
        current_swatch_height = swatch_height

        if position in ['top', 'bottom']:
            if i == len(colors) - 1: # Ostatnia próbka może być szersza
                current_swatch_width += extra_width_for_last_swatch
            x0 = swatch_x_start + i * swatch_width
            x1 = x0 + current_swatch_width
            y0 = swatch_y
            y1 = swatch_y + swatch_size
        else: # left or right
            if i == len(colors) - 1: # Ostatnia próbka może być wyższa
                current_swatch_height += extra_height_for_last_swatch
            y0 = swatch_y_start + i * swatch_height
            y1 = y0 + current_swatch_height
            x0 = swatch_x
            x1 = swatch_x + swatch_size

        draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
        
        # Rysowanie ramek próbek
        if swatch_border_thickness > 0:
            # Górna linia
            if not (remove_adjacent_border and position == 'top' and border_thickness == 0):
                 draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            # Dolna linia
            if not (remove_adjacent_border and position == 'bottom' and border_thickness == 0):
                 draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            # Lewa linia
            if not (remove_adjacent_border and position == 'left' and border_thickness == 0):
                 draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            # Prawa linia
            if not (remove_adjacent_border and position == 'right' and border_thickness == 0):
                 draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

            # Wewnętrzne linie między próbkami, jeśli nie są przy krawędzi obrazu
            if position in ['top', 'bottom']:
                if i > 0: # Wewnętrzna lewa linia
                    draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            else: # left, right
                if i > 0: # Wewnętrzna górna linia
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
        type=allowed_types # Użyj argumentu 'type' dla walidacji po stronie klienta
    )

    # Walidacja po stronie serwera (dodatkowa, na wypadek gdyby 'type' nie zadziałało idealnie)
    valid_files_after_upload = []
    if uploaded_files:
        valid_extensions_tuple = tuple(f".{ext}" for ext in allowed_types)
        for file in uploaded_files:
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

    output_format = st.selectbox("Format wyjściowy", ["JPG", "PNG", "WEBP"], key="output_format")
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

    # Użycie kolumn dla lepszego rozmieszczenia przełączników
    row1_layout = st.columns(2)
    row2_layout = st.columns(2)
    
    if row1_layout[0].toggle("Góra", key="pos_top"):
        positions.append("top")
    if row1_layout[1].toggle("Lewo", key="pos_left"):
        positions.append("left")
    if row2_layout[0].toggle("Dół", value=True, key="pos_bottom"): # Domyślnie zaznaczone
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
        "MEDIANCUT": Image.Quantize.MEDIAN_CUT, # Zaktualizowane stałe Pillow
        "MAXCOVERAGE": Image.Quantize.MAXCOVERAGE,
        "FASTOCTREE": Image.Quantize.FASTOCTREE
    }
    quantize_method = quant_method_map[quant_method_label]

    num_colors = st.slider("Liczba próbek", 2, 12, 6, key="num_colors")
    swatch_size = st.slider("Rozmiar próbki (px)", 20, 200, 100, key="swatch_size")

with col3:
    st.subheader("🖼️ Ramki")
    border_thickness_percent = st.slider("Grubość ramki obrazu (% szerokości)", 0, 10, 0, key="border_thickness_percent")
    border_color = st.color_picker("Kolor ramki obrazu", "#FFFFFF", key="border_color")
    swatch_border_thickness = st.slider("Grubość ramki próbki (px)", 0, 10, 1, key="swatch_border_thickness") # Domyślnie 1px
    swatch_border_color = st.color_picker("Kolor ramki próbki", "#CCCCCC", key="swatch_border_color") # Ciemniejszy domyślny
    remove_adjacent_border = st.checkbox("Dopasuj próbki do krawędzi obrazu (usuń przyległe ramki)", value=True, key="remove_adjacent_border")


# --- Process & Preview ---
if uploaded_files and positions:
    st.markdown("---") # Linia separująca
    st.subheader("🖼️ Podglądy")
    
    # Użyj st.empty() do stworzenia elementu, którego zawartość możemy dynamicznie aktualizować.
    # Ten element będzie zawierał całą strefę podglądu.
    preview_display_area = preview_container.empty()

    # Lista do przechowywania HTML każdego indywidualnego elementu podglądu
    individual_preview_html_parts = []
    
    # Bufor dla pliku ZIP
    zip_buffer = io.BytesIO()

    with st.spinner("⏳ Generowanie podglądów..."):
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, compresslevel=zipfile.ZIP_STORED) as zipf: # ZIP_STORED dla szybszego pakowania bez kompresji obrazów
            for uploaded_file in uploaded_files:
                try:
                    # Sprawdzenie integralności obrazu
                    test_image = Image.open(uploaded_file)
                    test_image.verify()  # Może rzucić wyjątek dla uszkodzonych plików
                    uploaded_file.seek(0) # Resetuj wskaźnik pliku po verify()
                    image = Image.open(uploaded_file)
                except UnidentifiedImageError:
                    st.warning(f"⚠️ Nie można zidentyfikować pliku obrazu: `{uploaded_file.name}`. Pominięto.")
                    continue
                except Exception as e:
                    st.warning(f"⚠️ `{uploaded_file.name}` nie mógł zostać załadowany lub jest uszkodzony ({e}). Pominięto.")
                    continue

                try:
                    w, h = image.size
                    # Podstawowa walidacja rozmiaru, aby uniknąć problemów z bardzo małymi/dużymi obrazami
                    if not (10 <= w <= 10000 and 10 <= h <= 10000):
                        st.warning(f"⚠️ `{uploaded_file.name}` ma nieobsługiwaną rozdzielczość ({w}x{h}). Zakres: 10-10000px. Pominięto.")
                        continue
                    
                    # Konwersja do RGB, jeśli obraz ma kanał alfa lub jest w innym trybie
                    if image.mode not in ("RGB", "L"): # L to skala szarości
                         image = image.convert("RGB")
                    
                    palette = extract_palette(image, num_colors, quantize_method=quantize_method)
                    if not palette: # Jeśli ekstrakcja palety się nie powiodła
                        st.warning(f"⚠️ Nie udało się wyekstrahować palety dla `{uploaded_file.name}`. Pominięto generowanie próbek dla tego obrazu.")
                        # Można dodać oryginalny obraz do ZIP lub pominąć
                        # For now, skip swatch generation for this image
                        # Continue to next file or handle by adding original image to zip
                        # To simply skip, we can `continue` here if we don't want to process it further.
                        # However, we might still want to add the original image to the zip if no palette.
                        # Let's assume for now that if no palette, we don't generate layouts.
                        # The draw_layout function handles empty palettes.
                        pass # draw_layout should handle empty palette

                except Exception as e:
                    st.error(f"⚠️ Błąd przetwarzania `{uploaded_file.name}`: {e}. Pominięto.")
                    continue

                # Obliczanie grubości ramki w pikselach
                border_px = int(image.width * (border_thickness_percent / 100))

                for pos_idx, pos in enumerate(positions):
                    try:
                        result_img = draw_layout(
                            image.copy(), palette, pos, border_px, swatch_border_thickness,
                            border_color, swatch_border_color, swatch_size, remove_adjacent_border
                        )

                        if resize_option == "Skaluj (%)" and scale_percent != 100:
                            new_w = int(result_img.width * scale_percent / 100)
                            new_h = int(result_img.height * scale_percent / 100)
                            if new_w > 0 and new_h > 0:
                                result_img = result_img.resize((new_w, new_h), Image.Resampling.LANCZOS) # Użyj Resampling
                            else:
                                st.warning(f"Nie można przeskalować obrazu {uploaded_file.name}_{pos} do zerowych wymiarów. Użyto oryginalnych.")


                        # Zapis do pliku ZIP
                        img_byte_arr = io.BytesIO()
                        # Upewnij się, że nazwa pliku jest unikalna i poprawna
                        base_name, _ = uploaded_file.name.rsplit('.', 1)
                        safe_base_name = "".join(c if c.isalnum() or c in (' ', '.', '_') else '_' for c in base_name).rstrip()
                        name_for_zip = f"{safe_base_name}_{pos}.{extension}"
                        
                        save_params = {}
                        if img_format == "JPEG":
                            save_params['quality'] = 95 # Dobra jakość dla JPG
                        elif img_format == "WEBP":
                            save_params['quality'] = 90 # Dobra jakość dla WEBP
                            save_params['lossless'] = (output_format == "WEBP" and st.session_state.get('webp_lossless', False)) # Przykładowa opcja

                        result_img.save(img_byte_arr, format=img_format, **save_params)
                        zipf.writestr(name_for_zip, img_byte_arr.getvalue())

                        # Generowanie HTML dla tego pojedynczego podglądu
                        # Użyj kopii do wyświetlania, można ją zmniejszyć dla szybszego renderowania
                        preview_img_for_display = result_img.copy()
                        preview_img_for_display.thumbnail((200, 200)) # Zmniejsz do max 200px szerokości/wysokości dla podglądu

                        with io.BytesIO() as buffer_display:
                            preview_img_for_display.save(buffer_display, format="PNG") # Zawsze PNG dla base64 w HTML
                            img_base64 = base64.b64encode(buffer_display.getvalue()).decode("utf-8")
                        
                        # HTML dla jednego elementu podglądu - używa klas CSS zdefiniowanych wyżej
                        single_item_html = f"<div class='preview-item'>"
                        single_item_html += f"<div class='preview-item-name'>{name_for_zip}</div>"
                        single_item_html += f"<img src='data:image/png;base64,{img_base64}' alt='Podgląd {name_for_zip}'>"
                        single_item_html += "</div>"
                        
                        individual_preview_html_parts.append(single_item_html)

                        # Skonstruuj pełny HTML dla strefy podglądu z dotychczasowymi elementami
                        current_full_html_content = (
                            # Style są już globalnie zdefiniowane, więc nie trzeba ich tu powtarzać
                            # chyba że są specyficzne tylko dla tego bloku i nie ma ich w st.markdown na górze.
                            # Dla pewności, można tu dodać style dla #preview-zone i .preview-item, jeśli nie ma ich globalnie.
                            # Ale ponieważ są zdefiniowane na początku, nie są tu potrzebne.
                            "<div id='preview-zone'>"
                            + "\n".join(individual_preview_html_parts) +
                            "</div>"
                        )
                        # Zaktualizuj zawartość elementu st.empty()
                        preview_display_area.markdown(current_full_html_content, unsafe_allow_html=True)
                    
                    except Exception as e_layout:
                        st.error(f"Błąd podczas tworzenia układu dla {uploaded_file.name} ({pos}): {e_layout}")
                        # Można dodać logowanie błędu do konsoli dla dewelopera
                        # print(f"Error during layout generation for {uploaded_file.name} ({pos}): {e_layout}", file=sys.stderr)


        zip_buffer.seek(0)

    # Przycisk pobierania (poza spinnerem, po zakończeniu przetwarzania)
    # Sprawdź, czy bufor ZIP zawiera jakiekolwiek dane przed wyświetleniem przycisku
    if zip_buffer.getbuffer().nbytes > 500: # Plik ZIP zawsze ma pewien narzut, więc > 0 nie wystarczy
        st.download_button(
            label=f"📦 Pobierz wszystko jako ZIP ({extension.upper()})",
            data=zip_buffer,
            file_name=f"PróbkiKolorów_{output_format.lower()}.zip",
            mime="application/zip",
            use_container_width=True,
            key="download_zip"
        )
    elif uploaded_files and positions : # Jeśli były pliki i pozycje, ale nic nie trafiło do ZIP
        st.warning("⚠️ Nie wygenerowano żadnych obrazów do pobrania. Sprawdź komunikaty o błędach powyżej.")

elif uploaded_files and not positions:
    st.warning("⚠️ Wybierz przynajmniej jedną pozycję dla próbek kolorów, aby wygenerować podglądy.")


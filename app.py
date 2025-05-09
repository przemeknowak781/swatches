import streamlit as st
from PIL import Image, ImageDraw
import numpy as np
from sklearn.cluster import KMeans
import io
import zipfile
import os
import base64

# Function to extract dominant colors
def extract_palette(image, num_colors=6):
    img = image.convert('RGB')
    data = np.array(img).reshape((-1, 3))
    kmeans = KMeans(n_clusters=num_colors, random_state=42).fit(data)
    return kmeans.cluster_centers_.astype(int)

# Drawing function
def draw_layout(image, colors, position, border_thickness, swatch_border_thickness, border_color, swatch_border_color, swatch_size, remove_adjacent_border):
    img_w, img_h = image.size
    border = border_thickness

    if position == 'top':
        canvas = Image.new("RGB", (img_w + 2 * border, img_h + swatch_size + 2 * border), border_color)
        canvas.paste(image, (border, swatch_size + border))
        swatch_y = border
        swatch_width = img_w // len(colors)
        for i, color in enumerate(colors):
            x0 = border + i * swatch_width
            x1 = border + (i + 1) * swatch_width
            y0 = swatch_y
            y1 = swatch_y + swatch_size
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
            if not remove_adjacent_border or i != 0:
                draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or i != len(colors) - 1:
                draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

    elif position == 'bottom':
        canvas = Image.new("RGB", (img_w + 2 * border, img_h + swatch_size + 2 * border), border_color)
        canvas.paste(image, (border, border))
        swatch_y = border + img_h
        swatch_width = img_w // len(colors)
        for i, color in enumerate(colors):
            x0 = border + i * swatch_width
            x1 = border + (i + 1) * swatch_width
            y0 = swatch_y
            y1 = swatch_y + swatch_size
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
            if not remove_adjacent_border or i != 0:
                draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or i != len(colors) - 1:
                draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

    elif position == 'left':
        canvas = Image.new("RGB", (img_w + swatch_size + 2 * border, img_h + 2 * border), border_color)
        canvas.paste(image, (swatch_size + border, border))
        swatch_x = border
        swatch_height = img_h // len(colors)
        for i, color in enumerate(colors):
            y0 = border + i * swatch_height
            y1 = border + (i + 1) * swatch_height
            x0 = swatch_x
            x1 = swatch_x + swatch_size
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
            if not remove_adjacent_border or i != 0:
                draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or i != len(colors) - 1:
                draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

    elif position == 'right':
        canvas = Image.new("RGB", (img_w + swatch_size + 2 * border, img_h + 2 * border), border_color)
        canvas.paste(image, (border, border))
        swatch_x = border + img_w
        swatch_height = img_h // len(colors)
        for i, color in enumerate(colors):
            y0 = border + i * swatch_height
            y1 = border + (i + 1) * swatch_height
            x0 = swatch_x
            x1 = swatch_x + swatch_size
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
            if not remove_adjacent_border or i != 0:
                draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or i != len(colors) - 1:
                draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

    return canvas

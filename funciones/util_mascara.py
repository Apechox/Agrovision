"""Utilidades de máscara compartidas por madurez.py y manchas.py."""
import cv2
import numpy as np


def _kernel(radio):
    k = 2 * int(radio) + 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def mascara_reflejos(hsv, s_max, v_min, dilatar_px=0):
    """Reflejos especulares: píxeles muy claros y poco saturados (blanquecinos)."""
    s, v = hsv[..., 1], hsv[..., 2]
    ref = ((s <= s_max) & (v >= v_min)).astype(np.uint8) * 255
    if dilatar_px > 0:
        ref = cv2.dilate(ref, _kernel(dilatar_px))
    return ref


def erosionar(mask, px):
    if px <= 0:
        return mask
    return cv2.erode(mask, _kernel(px))


def apertura(mask, px):
    if px <= 0:
        return mask
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, _kernel(px))


def cierre(mask, px):
    if px <= 0:
        return mask
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _kernel(px))


def mascara_binaria(mask):
    """Normaliza cualquier máscara de entrada a uint8 0/255."""
    if mask.ndim == 3:
        mask = mask[..., 0]
    return (mask > 0).astype(np.uint8) * 255
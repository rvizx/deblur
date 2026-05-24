#!/usr/bin/env python3
"""Headless CLI wrapper for the deblur engine. Runs without a display."""

import os
import sys
import argparse

# Force headless pygame before import
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
pygame.init()
# Need a tiny dummy display for Surface operations
pygame.display.set_mode((1, 1))

import cv2
import numpy
import blurs
import deblur


class CLIDeblurrer(deblur.AbstractIterativeGhastDeblurrer):
    def __init__(self, blur_type="gaussian", radius=15, iterations=100,
                 start_intensity=4.0, end_intensity=3.0, bp_blur_strength=1.0):
        self.blur_type = blur_type
        self.radius = radius
        self.iteration_limit = iterations
        self.start_intensity = start_intensity
        self.end_intensity = end_intensity
        self.bp_blur_strength = bp_blur_strength
        super().__init__()

    def get_correction_intensity(self, iteration):
        if iteration >= self.iteration_limit:
            return self.end_intensity
        elif iteration <= 0:
            return self.start_intensity
        else:
            return self.start_intensity + (iteration / self.iteration_limit) * (self.end_intensity - self.start_intensity)

    def show_relative_error(self):
        return False

    def get_backpropagation_blur_strength(self) -> float:
        return self.bp_blur_strength

    def do_blur(self, surf: pygame.Surface, strength=1.0) -> pygame.Surface:
        effective_radius = round(strength * self.radius)
        if effective_radius > 0:
            blur_func = blurs.get_blur_func(self.blur_type)
            return blur_func(surf, effective_radius)
        else:
            return surf.copy()

    def get_iteration_limit(self) -> int:
        return self.iteration_limit


def main():
    parser = argparse.ArgumentParser(description="Headless image deblurrer")
    parser.add_argument("input", help="Path to blurred input image")
    parser.add_argument("-o", "--output", default="/output/deblurred.png", help="Output path")
    parser.add_argument("-t", "--blur-type", default="gaussian", choices=["gaussian", "box filter", "median filter"])
    parser.add_argument("-r", "--radius", type=int, default=15, help="Blur radius to reverse (default: 15)")
    parser.add_argument("-n", "--iterations", type=int, default=100, help="Number of iterations (default: 100)")
    parser.add_argument("--start-intensity", type=float, default=4.0)
    parser.add_argument("--end-intensity", type=float, default=3.0)
    parser.add_argument("--bp-blur-strength", type=float, default=1.0)
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Loading image: {args.input}")
    try:
        input_img = pygame.image.load(args.input)
    except pygame.error as e:
        print(f"ERROR: Failed to load image: {e}", file=sys.stderr)
        sys.exit(1)

    w, h = input_img.get_size()
    print(f"[*] Image size: {w}x{h}")
    print(f"[*] Blur type: {args.blur_type}, radius: {args.radius}, iterations: {args.iterations}")

    engine = CLIDeblurrer(
        blur_type=args.blur_type,
        radius=args.radius,
        iterations=args.iterations,
        start_intensity=args.start_intensity,
        end_intensity=args.end_intensity,
        bp_blur_strength=args.bp_blur_strength,
    )
    engine.set_target_image(input_img.convert())

    print(f"[*] Running {args.iterations} deblur iterations...")
    for i in range(args.iterations):
        engine.step()
        if (i + 1) % 10 == 0 or i == 0:
            print(f"    iteration {i + 1}/{args.iterations}  error={engine.get_error():.2f}")

    output_img = engine.get_output_image()
    if output_img is None:
        print("ERROR: Deblur produced no output", file=sys.stderr)
        sys.exit(1)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Use cv2 to save instead of pygame — more reliable in headless/read-only containers
    arr = pygame.surfarray.array3d(output_img)  # (W, H, 3) RGB
    arr = arr.transpose(1, 0, 2)  # (H, W, 3) — cv2 expects row-major
    arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    cv2.imwrite(args.output, arr_bgr)
    print(f"[+] Saved deblurred image to: {args.output}")


if __name__ == "__main__":
    main()

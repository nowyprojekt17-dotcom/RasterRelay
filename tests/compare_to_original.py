"""
Porownanie jak dobrze kazdy pipeline dopasowuje sie do ORYGINALNEGO obrazu.
Mierzy roznice miedzy wygenerowanym obszarem a otoczeniem w oryginale.
"""
import numpy as np
from PIL import Image
from scipy import ndimage

# Load images
original = np.array(Image.open(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\rr-04-car-logo-clean-panel-0131279d-source.png").convert("RGB"))
old_result = np.array(Image.open(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\compare_old_result.png").convert("RGB"))
new_result = np.array(Image.open(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\compare_new_result.png").convert("RGB"))
mask = np.array(Image.open(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\rr-04-car-logo-clean-panel-0131279d-mask.png").convert("L")) > 128

print("=" * 70)
print("JAKOSC DOPASOWANIA DO ORYGINALU")
print("=" * 70)

# 1. Color match - how well does generated area match surrounding original?
print("\n1. DOPASOWANIE KOLOROW (mean RGB w wygenerowanym vs otoczenie):")

# Get surrounding original area (ring around mask)
dilated = ndimage.binary_dilation(mask, iterations=10)
surrounding = ~mask & dilated

orig_surrounding_color = original[surrounding].mean(axis=0)
old_gen_color = old_result[mask].mean(axis=0)
new_gen_color = new_result[mask].mean(axis=0)

old_color_diff = np.abs(old_gen_color - orig_surrounding_color).mean()
new_color_diff = np.abs(new_gen_color - orig_surrounding_color).mean()

print(f"   Oryginal (otoczenie): RGB({orig_surrounding_color[0]:.1f}, {orig_surrounding_color[1]:.1f}, {orig_surrounding_color[2]:.1f})")
print(f"   STARY wynik:          RGB({old_gen_color[0]:.1f}, {old_gen_color[1]:.1f}, {old_gen_color[2]:.1f}) -> roznica: {old_color_diff:.2f}")
print(f"   NOWY wynik:           RGB({new_gen_color[0]:.1f}, {new_gen_color[1]:.1f}, {new_gen_color[2]:.1f}) -> roznica: {new_color_diff:.2f}")
print(f"   Poprawa: {((old_color_diff - new_color_diff) / old_color_diff * 100):.1f}%")

# 2. Edge continuity - how smooth is the transition at mask boundary?
print("\n2. PLYNNOSC PRZEJSCIA NA KRAWEDZI (gradient przy krawedzi maski):")

def edge_smoothness(img, mask):
    """Measure how smooth the transition is at mask boundary."""
    # Get pixels at boundary
    eroded = ndimage.binary_erosion(mask, iterations=1)
    boundary = mask & ~eroded

    # For each boundary pixel, find nearest outside pixel and compute difference
    ys, xs = np.where(boundary)
    diffs = []
    for i in range(0, len(ys), 2):  # sample every 2nd
        y, x = ys[i], xs[i]
        # Search for outside pixel
        for r in range(1, 5):
            for dy in range(-r, r+1):
                for dx in range(-r, r+1):
                    ny, nx = y+dy, x+dx
                    if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1]:
                        if not mask[ny, nx]:
                            diff = np.abs(img[y,x].astype(float) - img[ny,nx].astype(float)).mean()
                            diffs.append(diff)
                            break
                else:
                    continue
                break
            else:
                continue
            break
    return np.mean(diffs) if diffs else 0

old_smooth = edge_smoothness(old_result, mask)
new_smooth = edge_smoothness(new_result, mask)
print(f"   STARY smoothness: {old_smooth:.4f} (nizsz = lepiej)")
print(f"   NOWY smoothness: {new_smooth:.4f} (nizsz = lepiej)")
print(f"   Poprawa: {((old_smooth - new_smooth) / old_smooth * 100):.1f}%")

# 3. Texture match - does generated area have similar texture to surrounding?
print("\n3. DOPASOWANIE TEKSTURY (wariancja lokalna):")

def texture_match(img, mask):
    """Compare texture variance in generated vs surrounding area."""
    gen_region = mask & ndimage.binary_erosion(mask, iterations=10)
    surr_region = ~mask & ndimage.binary_dilation(mask, iterations=10) & ndimage.binary_erosion(~mask, iterations=5)

    if gen_region.sum() < 100 or surr_region.sum() < 100:
        return 0, 0

    gray = img.mean(axis=2)

    def local_var(region):
        ys, xs = np.where(region)
        vars = []
        for i in range(0, len(ys), 8):
            y, x = ys[i], xs[i]
            patch = gray[max(0,y-4):y+5, max(0,x-4):x+5]
            if patch.shape == (9, 9):
                vars.append(patch.var())
        return np.mean(vars) if vars else 0

    gen_var = local_var(gen_region)
    surr_var = local_var(surr_region)
    return gen_var, surr_var

old_gen_var, old_surr_var = texture_match(old_result, mask)
new_gen_var, new_surr_var = texture_match(new_result, mask)
orig_gen_var, orig_surr_var = texture_match(original, mask)

print(f"   Oryginal - generowany: {orig_gen_var:.1f}, otoczenie: {orig_surr_var:.1f}, ratio: {orig_gen_var/orig_surr_var:.2f}")
print(f"   STARY    - generowany: {old_gen_var:.1f}, otoczenie: {old_surr_var:.1f}, ratio: {old_gen_var/old_surr_var:.2f}")
print(f"   NOWY     - generowany: {new_gen_var:.1f}, otoczenie: {new_surr_var:.1f}, ratio: {new_gen_var/new_surr_var:.2f}")

# Ideal ratio is 1.0 (same texture)
old_ratio_dev = abs(old_gen_var/old_surr_var - 1.0)
new_ratio_dev = abs(new_gen_var/new_surr_var - 1.0)
print(f"   Odchylenie od idealu (1.0): STARY={old_ratio_dev:.2f}, NOWY={new_ratio_dev:.2f}")
print(f"   Poprawa: {((old_ratio_dev - new_ratio_dev) / old_ratio_dev * 100):.1f}%")

# 4. Overall score
print("\n" + "=" * 70)
print("OCENA OGOLNA:")
print("=" * 70)

color_improvement = (old_color_diff - new_color_diff) / old_color_diff * 100
smooth_improvement = (old_smooth - new_smooth) / old_smooth * 100
texture_improvement = (old_ratio_dev - new_ratio_dev) / old_ratio_dev * 100

print(f"   Dopasowanie kolorow: {color_improvement:+.1f}%")
print(f"   Plynnosc przejscia:  {smooth_improvement:+.1f}%")
print(f"   Dopasowanie tekstury: {texture_improvement:+.1f}%")

avg = (color_improvement + smooth_improvement + texture_improvement) / 3
print(f"\n   SREDNIA POPRAWA: {avg:+.1f}%")

if avg > 5:
    print("\n   [KONKLUZJA] Nowy pipeline jest WYRAZNIE LEPSZY")
elif avg > 0:
    print("\n   [KONKLUZJA] Nowy pipeline jest NIECO LEPSZY")
else:
    print("\n   [KONKLUZJA] Brak wyraznej poprawy lub pogorszenie")

print("=" * 70)

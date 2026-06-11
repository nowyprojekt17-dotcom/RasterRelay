"""
Szczegolowa analiza roznic miedzy starym a nowym pipeline'em.
Pokazuje roznice na krawedziach maski i w wewnatrz wygenerowanego obszaru.
"""
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt

# Load images
old_img = np.array(Image.open(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\compare_old_result.png").convert("RGB"))
new_img = np.array(Image.open(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\compare_new_result.png").convert("RGB"))
mask = np.array(Image.open(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\rr-04-car-logo-clean-panel-0131279d-mask.png").convert("L")) > 128

print("=" * 70)
print("SZCZEGÓŁOWA ANALIZA RÓŻNIC")
print("=" * 70)

# 1. Global difference
diff = np.abs(old_img.astype(float) - new_img.astype(float))
print(f"\n1. RÓŻNICE GLOBALNE:")
print(f"   Średnia różnica: {diff.mean():.4f} (na skali 0-255)")
print(f"   Maks różnica: {diff.max():.4f}")
print(f"   Mediana różnicy: {np.median(diff):.4f}")

# 2. Difference in generated area vs original area
gen_diff = diff[mask].mean()
orig_diff = diff[~mask].mean()
print(f"\n2. RÓŻNICE W OBSZARACH:")
print(f"   Wewnątrz maski (wygenerowane): {gen_diff:.4f}")
print(f"   Na zewnątrz maski (oryginał): {orig_diff:.4f}")
print(f"   Ratio: {gen_diff / orig_diff:.2f}x")

# 3. Edge analysis - differences at mask boundary
from scipy import ndimage
eroded_mask = ndimage.binary_erosion(mask, iterations=3)
dilated_mask = ndimage.binary_dilation(mask, iterations=3)

# Ring just inside mask
inner_ring = mask & ~eroded_mask
# Ring just outside mask
outer_ring = ~mask & dilated_mask

inner_diff = diff[inner_ring].mean()
outer_diff = diff[outer_ring].mean()
print(f"\n3. RÓŻNICE NA KRAWĘDZIACH MASKI:")
print(f"   Wewnętrzny pierścień (3px od krawędzi): {inner_diff:.4f}")
print(f"   Zewnętrzny pierścień (3px od krawędzi): {outer_diff:.4f}")

# 4. Color statistics in generated area
print(f"\n4. STATYSTYKI KOLORÓW W WYGENEROWANYM OBSZARZE:")
old_gen = old_img[mask]
new_gen = new_img[mask]
print(f"   STARY - RGB mean: ({old_gen[:,0].mean():.1f}, {old_gen[:,1].mean():.1f}, {old_gen[:,2].mean():.1f})")
print(f"   NOWY - RGB mean: ({new_gen[:,0].mean():.1f}, {new_gen[:,1].mean():.1f}, {new_gen[:,2].mean():.1f})")
print(f"   Różnica: ({new_gen[:,0].mean() - old_gen[:,0].mean():.1f}, {new_gen[:,1].mean() - old_gen[:,1].mean():.1f}, {new_gen[:,2].mean() - old_gen[:,2].mean():.1f})")

# 5. Texture analysis (local variance)
print(f"\n5. TEKSTURA (lokalna wariancja w wygenerowanym obszarze):")
def local_var(img, region, patch=5):
    gray = img.mean(axis=2)
    ys, xs = np.where(region)
    vars = []
    for i in range(0, len(ys), 10):
        y, x = ys[i], xs[i]
        y1, y2 = max(0, y-patch), min(gray.shape[0], y+patch)
        x1, x2 = max(0, x-patch), min(gray.shape[1], x+patch)
        vars.append(gray[y1:y2, x1:x2].var())
    return np.mean(vars) if vars else 0

old_var = local_var(old_img, mask & ndimage.binary_erosion(mask, iterations=10))
new_var = local_var(new_img, mask & ndimage.binary_erosion(mask, iterations=10))
print(f"   STARY wariancja: {old_var:.2f}")
print(f"   NOWY wariancja: {new_var:.2f}")
print(f"   Zmiana: {((new_var - old_var) / old_var * 100):.1f}%")

# 6. Save difference visualization
diff_vis = (diff / diff.max() * 255).astype(np.uint8)
diff_img = Image.fromarray(diff_vis)
diff_img.save(r"C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\compare_diff_visualization.png")
print(f"\n6. ZAPISANO wizualizację różnic: compare_diff_visualization.png")
print(f"   (jasne obszary = duże różnice między starym a nowym)")

# 7. Summary
print("\n" + "=" * 70)
print("PODSUMOWANIE:")
print("=" * 70)
if gen_diff > orig_diff * 2:
    print("[OK] Różnice są skoncentrowane w wygenerowanym obszarze (dobrze!)")
else:
    print("[?] Różnice rozłożone równomiernie (nieoczekiwane)")

if inner_diff > outer_diff:
    print("[OK] Największe różnice przy krawędziach maski (gdzie postprocessing działa)")
else:
    print("[?] Różnice nie są przy krawędziach (problem z metryką?)")

if new_var > old_var * 1.1:
    print("[OK] Nowy pipeline ma więcej tekstury/ziarna (cel GrainTransfer)")
elif new_var < old_var * 0.9:
    print("[!] Nowy pipeline ma mniej tekstury (nieoczekiwane)")
else:
    print("[~] Tekstura podobna (GrainTransfer może nie działać?)")

print("=" * 70)

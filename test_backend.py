
from PIL import Image
from process_satellite import (
    load_feature_extractor,
    analyze_image
)

print("Loading ResNet50V2...")

model = load_feature_extractor()

print("Model loaded successfully!")
print("Input shape:", model.input_shape)
print("Output shape:", model.output_shape)

print("\nCreating test image...")

image = Image.new(
    "RGB",
    (640, 640),
    color=(50, 130, 60)
)

print("Running analysis...")

result = analyze_image(image, model)

print("\nAnalysis complete!")
print("Total tiles:", result["total_tiles"])

print("\nTile report:")
print(result["report"].head())

result["overlay"].save("outputs/test_overlay.png")
result["report"].to_csv(
    "outputs/test_report.csv",
    index=False
)

print("\nFiles generated successfully!")

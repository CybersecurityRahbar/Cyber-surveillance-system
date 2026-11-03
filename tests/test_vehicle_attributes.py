import numpy as np

from traffic_surveillance.vision.vehicle_attributes import PretrainedVehicleAttributes


def test_twin_car_prediction_preserves_make_model_and_year_metadata():
    classifier = object.__new__(PretrainedVehicleAttributes)
    classifier._to_pil = lambda crop: crop
    classifier._predict = lambda model, transform, image: (
        [(2, 0.88), (4, 0.07), (1, 0.03)]
        if model == "colour"
        else [(0, 0.93), (1, 0.04), (2, 0.02)]
    )
    classifier._colour_model = "colour"
    classifier._colour_transform = None
    classifier._make_model_model = "make-model"
    classifier._make_transform = None
    classifier._make_model_labels = [
        "Toyota Camry 2012",
        "Toyota Corolla 2011",
        "Honda Accord 2012",
    ]
    classifier._make_model_classes = [
        {
            "class_id": 0, "label": "Toyota Camry 2012",
            "make": "Toyota", "model": "Camry", "year": "2012",
        },
        {
            "class_id": 1, "label": "Toyota Corolla 2011",
            "make": "Toyota", "model": "Corolla", "year": "2011",
        },
        {
            "class_id": 2, "label": "Honda Accord 2012",
            "make": "Honda", "model": "Accord", "year": "2012",
        },
    ]

    result = classifier.classify(np.zeros((32, 32, 3), dtype=np.uint8))

    make_model = result["make_model_model"]
    assert make_model["label"] == "Toyota Camry 2012"
    assert make_model["make"] == "Toyota"
    assert make_model["model"] == "Camry"
    assert make_model["year"] == "2012"
    assert make_model["model_repository"] == "twincar-group2/twincar-classifier"
    assert result["vehicle_color_model"]["label"] == "blue"

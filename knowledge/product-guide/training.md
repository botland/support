# Model training and customization

OwnEdge appliances support **training and customization** of models on hardware you own — useful when generic open models need domain adaptation.

## Functional outcomes

- Fine-tune or adapt models using customer data that stays local
- Deploy the resulting model through the console **Models** page (local path or catalog source as appropriate)
- Iterate without sending training corpora to a public cloud trainer

## Practical notes

- Training is heavier than inference: plan GPU memory, disk, and time accordingly
- Larger tiers (Studio / Forge) are better suited to serious training jobs
- After training, treat the artifact like any other model deployment: validate, place, enable, monitor

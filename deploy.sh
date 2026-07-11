#!/bin/bash
echo "🚀 Building and Deploying bidding-app..."
az acr build --registry tendertentaclecr --image bidding-app:latest .
az containerapp update -n bidding-app -g tender-tentacle --image tendertentaclecr.azurecr.io/bidding-app:latest
echo "✅ Deployment of bidding-app complete!"

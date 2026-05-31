#!/bin/bash
set -e

# Change directory to the script's directory
cd "$(dirname "$0")"

echo "=== Packaging Stablecoin Regulatory Radar for AWS Lambda ==="

# Clean up any existing packaging artifacts
echo "Cleaning up old directories and archives..."
rm -rf package deployment.zip

# Create the package directory
mkdir -p package

# 1. Install all dependencies normally (pulls pure-python packages and standard wheels)
echo "Installing all dependencies from requirements.txt to ./package..."
pip install -r requirements.txt -t ./package

# 2. Overwrite compiled packages with Linux x86_64 wheels for the Lambda environment
echo "Overwriting compiled packages with Linux x86_64 wheels..."
pip install \
  --platform manylinux2014_x86_64 \
  --target=./package \
  --implementation cp \
  --python-version 3.11 \
  --only-binary=:all: \
  --upgrade \
  pydantic pydantic-core cryptography jiter

# Zip the dependencies
echo "Zipping dependencies..."
cd package
zip -r ../deployment.zip .
cd ..

# Append the main application file
echo "Zipping lambda_function.py..."
zip deployment.zip lambda_function.py

# Clean up the package folder
echo "Cleaning up temporary package folder..."
rm -rf package

echo "=== Packaging complete! Created 'deployment.zip' successfully. ==="

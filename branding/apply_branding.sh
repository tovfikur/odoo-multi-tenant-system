#!/bin/bash
set -e

echo "Applying Kdoo branding and color scheme to Odoo core..."

# Define paths
ODOO_ROOT="/usr/lib/python3/dist-packages/odoo"
ADDONS_PATH="$ODOO_ROOT/addons"
NEW_COLOR="#005B8C"  # Kendroo blue (replace with your desired color)
BRANDING_DIR="/mnt/branding"

# Verify Odoo root exists
if [ ! -d "$ODOO_ROOT" ]; then
    echo "Error: Odoo root directory ($ODOO_ROOT) not found. Please verify Odoo installation."
    exit 1
fi

# Step 1: Verify and replace favicon
echo "Replacing favicon..."
FAVICON_FILES=$(find "$ADDONS_PATH" -type f -name "favicon.ico" 2>/dev/null)
if [ -z "$FAVICON_FILES" ]; then
    echo "Warning: No favicon.ico files found in $ADDONS_PATH."
else
    for file in $FAVICON_FILES; do
        if cp "$BRANDING_DIR/img/favicon.ico" "$file"; then
            echo "Replaced favicon: $file"
        else
            echo "Error: Failed to replace favicon: $file"
        fi
    done
fi

# Step 2: Verify and replace logo
echo "Replacing logo..."
LOGO_FILES=$(find "$ADDONS_PATH" -type f -name "logo*.png" 2>/dev/null)
if [ -z "$LOGO_FILES" ]; then
    echo "Warning: No logo files found in $ADDONS_PATH."
else
    for file in $LOGO_FILES; do
        if cp "$BRANDING_DIR/img/kdoo-logo.png" "$file"; then
            echo "Replaced logo: $file"
        else
            echo "Error: Failed to replace logo: $file"
        fi
    done
fi

# Step 3: Change primary color in SCSS files
echo "Updating color scheme..."
SCSS_FILES=$(find "$ADDONS_PATH" -type f -name "*.scss" -exec grep -l "\$o-brand-primary" {} \; 2>/dev/null)
if [ -z "$SCSS_FILES" ]; then
    echo "Error: No SCSS files with \$o-brand-primary found. Please verify Odoo installation."
    exit 1
fi

for file in $SCSS_FILES; do
    # Backup original file
    if cp "$file" "$file.bak"; then
        echo "Backed up $file"
    else
        echo "Error: Failed to backup $file"
        continue
    fi
    # Replace $o-brand-primary and $o-brand-odoo
    if sed -i "s|\$o-brand-primary: #[0-9a-fA-F]\{6\}|\$o-brand-primary: $NEW_COLOR|g" "$file"; then
        echo "Updated \$o-brand-primary in $file"
    else
        echo "Error: Failed to update \$o-brand-primary in $file"
        mv "$file.bak" "$file"
        continue
    fi
    sed -i "s|\$o-brand-odoo: #[0-9a-fA-F]\{6\}|\$o-brand-odoo: $NEW_COLOR|g" "$file" 2>/dev/null || true
    echo "Updated \$o-brand-odoo in $file (if present)"
done

# Step 4: Replace 'Odoo' with 'Kdoo' and 'odoo.com' with 'kendroo.io'
echo "Applying text branding..."
TEXT_FILES=$(find "$ODOO_ROOT" -type f \( -name "*.py" -o -name "*.xml" -o -name "*.js" -o -name "*.po" \) ! -path "*/tests/*" ! -name "*odoo*.py" 2>/dev/null)
if [ -z "$TEXT_FILES" ]; then
    echo "Warning: No text files found for branding replacement."
else
    for file in $TEXT_FILES; do
        if cp "$file" "$file.bak"; then
            echo "Backed up $file"
        else
            echo "Error: Failed to backup $file"
            continue
        fi
        if sed -i 's/Odoo/Kdoo/g' "$file"; then
            echo "Replaced 'Odoo' in $file"
        else
            echo "Error: Failed to replace 'Odoo' in $file"
            mv "$file.bak" "$file"
            continue
        fi
        if sed -i 's/odoo\.com/kendroo\.io/g' "$file"; then
            echo "Replaced 'odoo.com' in $file"
        else
            echo "Error: Failed to replace 'odoo.com' in $file"
            mv "$file.bak" "$file"
            continue
        fi
    done
fi

echo "Kdoo branding and color scheme applied successfully."
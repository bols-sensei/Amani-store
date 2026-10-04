/* Amani — design system Tailwind (tokens Stitch).
 * Partagé par toutes les pages : <script src="../shared/js/tailwind.config.js"></script>
 * À charger APRÈS https://cdn.tailwindcss.com */
window.tailwind = window.tailwind || {};
tailwind.config = {
  "darkMode": "class",
  "theme": {
    "extend": {
      "borderRadius": {
        "DEFAULT": "0.25rem",
        "full": "9999px",
        "lg": "0.5rem",
        "xl": "0.75rem"
      },
      "colors": {
        "background": "#fbf9f6",
        "error": "#ba1a1a",
        "error-container": "#ffdad6",
        "inverse-on-surface": "#f2f0ed",
        "inverse-primary": "#e6c093",
        "inverse-surface": "#30312f",
        "on-background": "#1b1c1a",
        "on-error": "#ffffff",
        "on-error-container": "#93000a",
        "on-primary": "#ffffff",
        "on-primary-container": "#fff8f4",
        "on-primary-fixed": "#2a1800",
        "on-primary-fixed-variant": "#5c421f",
        "on-secondary": "#ffffff",
        "on-secondary-container": "#6c6158",
        "on-secondary-fixed": "#221a13",
        "on-secondary-fixed-variant": "#4f453d",
        "on-surface": "#1b1c1a",
        "on-surface-variant": "#4e453b",
        "on-tertiary": "#ffffff",
        "on-tertiary-container": "#e8ffef",
        "on-tertiary-fixed": "#002113",
        "on-tertiary-fixed-variant": "#005236",
        "outline": "#80756a",
        "outline-variant": "#d2c4b7",
        "primary": "#715530",
        "primary-container": "#8c6d46",
        "primary-fixed": "#ffddb6",
        "primary-fixed-dim": "#e6c093",
        "secondary": "#675c53",
        "secondary-container": "#edddd1",
        "secondary-fixed": "#efe0d4",
        "secondary-fixed-dim": "#d3c4b9",
        "surface": "#fbf9f6",
        "surface-bright": "#fbf9f6",
        "surface-container": "#efeeeb",
        "surface-container-high": "#eae8e5",
        "surface-container-highest": "#e4e2df",
        "surface-container-low": "#f5f3f0",
        "surface-container-lowest": "#ffffff",
        "surface-dim": "#dbdad7",
        "surface-tint": "#765934",
        "surface-variant": "#e4e2df",
        "tertiary": "#006746",
        "tertiary-container": "#00835a",
        "tertiary-fixed": "#6ffbbe",
        "tertiary-fixed-dim": "#4edea3"
      },
      "fontFamily": {
        "body-lg": [
          "Inter"
        ],
        "body-md": [
          "Inter"
        ],
        "body-xl": [
          "Inter"
        ],
        "display-lg": [
          "Plus Jakarta Sans"
        ],
        "display-lg-mobile": [
          "Plus Jakarta Sans"
        ],
        "headline-lg": [
          "Plus Jakarta Sans"
        ],
        "headline-md": [
          "Plus Jakarta Sans"
        ],
        "headline-xl": [
          "Plus Jakarta Sans"
        ],
        "headline-xl-mobile": [
          "Plus Jakarta Sans"
        ],
        "label-lg": [
          "Inter"
        ],
        "label-md": [
          "Inter"
        ],
        "label-sm": [
          "Inter"
        ]
      },
      "fontSize": {
        "body-lg": [
          "16px",
          {
            "lineHeight": "24px",
            "fontWeight": "400"
          }
        ],
        "body-md": [
          "14px",
          {
            "lineHeight": "20px",
            "fontWeight": "400"
          }
        ],
        "body-xl": [
          "18px",
          {
            "lineHeight": "28px",
            "fontWeight": "400"
          }
        ],
        "display-lg": [
          "48px",
          {
            "lineHeight": "56px",
            "fontWeight": "700"
          }
        ],
        "display-lg-mobile": [
          "36px",
          {
            "lineHeight": "44px",
            "fontWeight": "700"
          }
        ],
        "headline-lg": [
          "24px",
          {
            "lineHeight": "32px",
            "fontWeight": "600"
          }
        ],
        "headline-md": [
          "20px",
          {
            "lineHeight": "28px",
            "fontWeight": "600"
          }
        ],
        "headline-xl": [
          "32px",
          {
            "lineHeight": "40px",
            "fontWeight": "600"
          }
        ],
        "headline-xl-mobile": [
          "26px",
          {
            "lineHeight": "34px",
            "fontWeight": "600"
          }
        ],
        "label-lg": [
          "14px",
          {
            "lineHeight": "20px",
            "fontWeight": "600"
          }
        ],
        "label-md": [
          "12px",
          {
            "lineHeight": "16px",
            "fontWeight": "500"
          }
        ],
        "label-sm": [
          "11px",
          {
            "lineHeight": "14px",
            "fontWeight": "600"
          }
        ]
      },
      "spacing": {
        "gutter": "1.25rem",
        "gutter-mobile": "0.75rem",
        "margin": "2rem",
        "margin-mobile": "1rem",
        "space-lg": "1.5rem",
        "space-md": "1rem",
        "space-sm": "0.5rem",
        "space-xl": "2.5rem",
        "space-xs": "0.25rem"
      }
    }
  }
};

# How to Add Your College Background Image

## Quick Steps:

1. **Save your college image** as `college-bg.jpg` 
2. **Place it in:** `frontend/public/` folder
3. The image will automatically appear as a subtle background on the Dashboard

## File Location:
```
frontend/
  └── public/
      └── college-bg.jpg  ← Put your image here
```

## Supported Formats:
- JPG/JPEG (recommended)
- PNG
- WebP

## Recommended Image Specifications:
- **Resolution:** 1920x1080 or higher
- **File Size:** Under 500KB for faster loading
- **Aspect Ratio:** 16:9 (landscape)

## Alternative: Use a URL

If your college image is already hosted online, you can use the URL directly:

1. Open `frontend/src/pages/Dashboard.jsx`
2. Find line with `backgroundImage: "url('/college-bg.jpg')"`
3. Replace with your URL: `backgroundImage: "url('https://your-college-website.com/image.jpg')"`

## Adjust Background Opacity

The background is set to 5% opacity (very subtle). To adjust:

1. Open `frontend/src/pages/Dashboard.jsx`
2. Find `className="... opacity-5 ..."`
3. Change opacity value:
   - `opacity-5` = 5% (very subtle - current)
   - `opacity-10` = 10% (subtle)
   - `opacity-20` = 20% (visible)
   - `opacity-30` = 30% (prominent)

## Current Setup:

✅ Dashboard is configured to use `/college-bg.jpg`
✅ Background is subtle (5% opacity) so it doesn't interfere with UI
✅ Background is fixed (doesn't scroll with content)

Just add your image file and refresh the browser!

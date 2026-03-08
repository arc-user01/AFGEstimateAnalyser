/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                background: "#0a0a0b",
                glass: "rgba(255, 255, 255, 0.03)",
                "glass-border": "rgba(255, 255, 255, 0.08)",
                primary: "#6366f1", // Indigo-500
                secondary: "#a855f7", // Purple-500
            }
        },
    },
    plugins: [],
}

// Local OFL fonts (no CDN: STRATA runs offline). latin + latin-ext only.
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-ext-400.css";
import "@fontsource/jetbrains-mono/latin-600.css";
import "@fontsource/jetbrains-mono/latin-ext-600.css";
import "@fontsource/big-shoulders-display/latin-700";
import "@fontsource/big-shoulders-display/latin-ext-700";
import "@fontsource/big-shoulders-display/latin-800";
import "@fontsource/big-shoulders-display/latin-ext-800";

export async function fontsReady(): Promise<void> {
  try {
    await Promise.all([
      document.fonts.load(`400 11px "JetBrains Mono"`), document.fonts.load(`600 11px "JetBrains Mono"`),
      document.fonts.load(`700 20px "Big Shoulders Display"`), document.fonts.load(`800 20px "Big Shoulders Display"`),
    ]);
  } catch { /* fall back to system fonts */ }
}

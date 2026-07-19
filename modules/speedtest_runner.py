"""Open Speedtest Custom page and auto-click Start."""

from __future__ import annotations

import threading
import time
import webbrowser
from typing import Callable


class SpeedtestLauncher:
    def __init__(
        self,
        url: str,
        on_line: Callable[[str], None],
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self.url = url
        self.on_line = on_line
        self.on_done = on_done
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            self.on_line(f"Membuka Speedtest: {self.url}")
            if self._try_selenium():
                return
            self.on_line("Selenium tidak tersedia / gagal — membuka browser biasa.")
            webbrowser.open(self.url)
            self.on_line(
                "Silakan klik tombol Start secara manual di halaman Speedtest."
            )
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done()

    def _try_selenium(self) -> bool:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.chrome.service import Service as ChromeService
            from selenium.webdriver.common.by import By
            from selenium.webdriver.edge.options import Options as EdgeOptions
            from selenium.webdriver.edge.service import Service as EdgeService
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            from webdriver_manager.chrome import ChromeDriverManager
            from webdriver_manager.microsoft import EdgeChromiumDriverManager
        except Exception as exc:
            self.on_line(f"Import selenium gagal: {exc}")
            return False

        driver = None
        try:
            # Prefer Edge on Windows
            try:
                options = EdgeOptions()
                options.add_argument("--start-maximized")
                service = EdgeService(EdgeChromiumDriverManager().install())
                driver = webdriver.Edge(service=service, options=options)
                self.on_line("Browser: Microsoft Edge")
            except Exception:
                options = ChromeOptions()
                options.add_argument("--start-maximized")
                service = ChromeService(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
                self.on_line("Browser: Google Chrome")

            driver.get(self.url)
            self.on_line("Halaman dimuat, mencari tombol Start...")

            wait = WebDriverWait(driver, 30)
            clicked = False
            selectors = [
                (By.CSS_SELECTOR, "button.start-button"),
                (By.CSS_SELECTOR, ".start-button"),
                (By.CSS_SELECTOR, "#start-button"),
                (By.CSS_SELECTOR, "button[aria-label*='Start' i]"),
                (By.XPATH, "//button[contains(translate(., 'START', 'start'), 'start')]"),
                (By.XPATH, "//*[contains(@class,'start') and (self::button or self::a or self::div)]"),
            ]

            for by, sel in selectors:
                if self._stop.is_set():
                    break
                try:
                    el = wait.until(EC.element_to_be_clickable((by, sel)))
                    el.click()
                    clicked = True
                    self.on_line("Tombol Start diklik otomatis.")
                    break
                except Exception:
                    continue

            if not clicked:
                # Try JS click on common Ookla custom start
                try:
                    driver.execute_script(
                        """
                        const candidates = [
                          ...document.querySelectorAll('button, a, div, span')
                        ];
                        const btn = candidates.find(el =>
                          /start|go|mulai/i.test((el.innerText || el.textContent || '').trim())
                          || /start/i.test(el.className || '')
                        );
                        if (btn) { btn.click(); return true; }
                        return false;
                        """
                    )
                    clicked = True
                    self.on_line("Tombol Start diklik via JavaScript.")
                except Exception:
                    self.on_line("Tombol Start tidak ditemukan otomatis.")

            # Keep browser open; user closes manually
            self.on_line("Speedtest berjalan di browser. Jangan tutup jendela browser.")
            # Wait a bit so result can appear while logging
            for _ in range(60):
                if self._stop.is_set():
                    break
                time.sleep(1)
            return True
        except Exception as exc:
            self.on_line(f"Selenium error: {exc}")
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            return False

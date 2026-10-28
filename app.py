import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from sanctum_keeper.database import KeeperDatabase
from sanctum_keeper.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    app.setApplicationName("The Sanctum Keeper")
    app.setOrganizationName("ObliqForge")

    # Keep persistent application data outside watched folders.
    local_app_data = Path(
        os.environ.get(
            "LOCALAPPDATA",
            str(Path.home() / "AppData" / "Local"),
        )
    )

    database_path = (
        local_app_data
        / "TheSanctumKeeper"
        / "keeper.sqlite3"
    )

    database = KeeperDatabase(database_path)

    window = MainWindow(database)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
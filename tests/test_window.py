from twomd.config import Settings, load_settings
from twomd.ui.main_window import MainWindow


def test_window_adds_files_once_and_persists_destination(qtbot, tmp_path):
    file = tmp_path / "documento.pdf"
    file.touch()
    path = tmp_path / "config" / "settings.json"
    window = MainWindow(Settings(), path)
    qtbot.addWidget(window)
    window.add_paths([file, file])
    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "Pendiente"
    assert window.persist(Settings(output_directory=str(tmp_path)))
    assert load_settings(path).output_directory == str(tmp_path)

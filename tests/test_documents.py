from twomd.documents import supported_documents


def test_documents_filter_and_deduplicate(tmp_path):
    word = tmp_path / "documento.DOCX"
    pdf = tmp_path / "plano.pdf"
    other = tmp_path / "notas.txt"
    for path in (word, pdf, other):
        path.touch()
    assert supported_documents([word, other, pdf, word, tmp_path]) == [
        word.resolve(),
        pdf.resolve(),
    ]

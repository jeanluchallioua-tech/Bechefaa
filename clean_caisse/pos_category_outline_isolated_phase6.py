"""Finition visuelle isolée des catégories POS BÉCHÉFAA.

Ajoute uniquement un liseré doré très fin (0,5 px) autour des boutons de
catégories de la caisse. Aucune logique métier, aucun filtrage et aucune donnée
ne sont modifiés.
"""


def register_pos_category_outline_isolated_phase6(app):
    if getattr(app, "_bechefaa_pos_category_outline_phase6", False):
        return
    original = app.view_functions.get("pos")
    if original is None:
        return

    addon = r'''
<style id="pos-category-outline-phase6-style">
.cats .cat{
  border:0.5px solid rgba(240,189,69,.72)!important;
}
.cats .cat.active{
  border-color:#f0bd45!important;
}
</style>
'''

    def pos_category_outline_view(*args, **kwargs):
        response = app.make_response(original(*args, **kwargs))
        try:
            if response.status_code == 200 and response.mimetype == "text/html":
                html = response.get_data(as_text=True)
                if "pos-category-outline-phase6-style" not in html:
                    html = html.replace("</body>", addon + "</body>")
                    response.set_data(html)
                    response.content_length = len(response.get_data())
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_category_outline_view
    app._bechefaa_pos_category_outline_phase6 = True

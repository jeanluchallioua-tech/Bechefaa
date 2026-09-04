# BÉCHÉFAA — intégrité UI commandes sur branche d'audit
# Corrige uniquement le runtime JS de l'environnement de test.

from pathlib import Path

BASE = Path(__file__).resolve().parent
CLOUD_JS = BASE / "static" / "cloud.js"
MARKER = "BECHEFAA_ORDER_UI_INTEGRITY_20260904"


def apply():
    src = CLOUD_JS.read_text(encoding="utf-8")
    if MARKER in src:
        return

    # 1) refreshOrders utilisait un nom de méthode inexistant dans la passerelle.
    src = src.replace(
        "        app.renderBoards();",
        "        app.refreshBoards?.();",
        1,
    )

    # 2) Le clic Modifier doit vérifier/recharger la commande depuis le serveur
    # avant de démarrer l'édition locale. Cela interdit l'édition d'une commande
    # fantôme présente uniquement dans le cache mémoire.
    old_listener = ''' document.addEventListener("click",e=>{\n   let b=e.target.closest("[data-view-order]");if(b){openOrder(b.dataset.viewOrder,false);return}\n   b=e.target.closest("[data-edit-order]");if(b){$x("#orderModal")?.classList.add("hidden");bridge()?.beginEditOrder?.(b.dataset.editOrder);return}\n   b=e.target.closest("[data-print-counter]");if(b){printOrder(b.dataset.printCounter,false);return}\n   b=e.target.closest("[data-print-delivery]");if(b){printOrder(b.dataset.printDelivery,true);return}\n   b=e.target.closest("[data-remove-edit]");if(b){b.closest("[data-edit-index]")?.remove();return}\n   b=e.target.closest('[data-view="history"],[data-qview="history"]');if(b)setTimeout(renderHistory,0);\n });'''

    new_listener = ''' document.addEventListener("click",async e=>{ /* BECHEFAA_ORDER_UI_INTEGRITY_20260904 */\n   let b=e.target.closest("[data-view-order]");if(b){openOrder(b.dataset.viewOrder,false);return}\n   b=e.target.closest("[data-edit-order]");if(b){\n     e.preventDefault();\n     const id=String(b.dataset.editOrder||"");\n     try{\n       const fresh=await apiX(`/api/orders/${encodeURIComponent(id)}?t=${Date.now()}`);\n       const list=bridge()?.getOrders?.();\n       if(Array.isArray(list)){\n         const i=list.findIndex(x=>String(x.id)===id);\n         if(i>=0)list[i]=fresh;else list.unshift(fresh);\n       }\n       $x("#orderModal")?.classList.add("hidden");\n       const ok=bridge()?.beginEditOrder?.(id);\n       if(!ok)alert("Cette commande ne peut plus être modifiée dans son statut actuel.");\n     }catch(err){\n       console.error("BÉCHÉFAA authoritative edit:",err);\n       alert("Impossible de charger cette commande depuis la base centrale. Aucune modification n'a été faite.");\n     }\n     return;\n   }\n   b=e.target.closest("[data-print-counter]");if(b){printOrder(b.dataset.printCounter,false);return}\n   b=e.target.closest("[data-print-delivery]");if(b){printOrder(b.dataset.printDelivery,true);return}\n   b=e.target.closest("[data-remove-edit]");if(b){b.closest("[data-edit-index]")?.remove();return}\n   b=e.target.closest('[data-view="history"],[data-qview="history"]');if(b)setTimeout(renderHistory,0);\n });'''

    if old_listener not in src:
        raise RuntimeError("gestionnaire Historique/Modifier introuvable")
    src = src.replace(old_listener, new_listener, 1)

    # 3) Fermeture robuste de la fenêtre Voir, en délégation de clic.
    # Elle fonctionne même si le binding window.load historique n'a pas été posé.
    close_guard = '''\n/* BECHEFAA_ORDER_MODAL_CLOSE_GUARD_20260904 */\ndocument.addEventListener("click",e=>{\n const close=e.target.closest?.("#closeOrderModal");\n if(!close)return;\n e.preventDefault();\n e.stopPropagation();\n document.getElementById("orderModal")?.classList.add("hidden");\n document.body.style.overflow="";\n document.documentElement.style.overflow="";\n},true);\n'''
    src += close_guard

    CLOUD_JS.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA ORDERS UI: Voir/Modifier autoritaires corrigés.")


apply()

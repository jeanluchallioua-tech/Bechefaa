"""Finition visuelle de l'activation audio Cuisine.

Ne modifie ni le polling ni la logique de notification. Le navigateur garde sa
contrainte d'interaction utilisateur, mais le bouton d'attente devient discret.
"""
from flask import request


def register_kitchen_audio_visual_fix(app):
    @app.after_request
    def kitchen_audio_visual_fix(response):
        if request.path != "/cuisine-preparation" or response.status_code != 200 or response.mimetype != "text/html":
            return response
        html = response.get_data(as_text=True)
        addon = r'''
<style id="kitchen-audio-visual-fix">
.phase33-audio{background:#161b20!important;color:#f0c15b!important;border:1px solid #6e572c!important;box-shadow:0 3px 12px rgba(0,0,0,.28)!important;padding:7px 10px!important;font-size:12px!important;border-radius:7px!important;right:10px!important;top:10px!important}
.phase33-audio.ready{background:#10271c!important;color:#9be4b7!important;border-color:#28593c!important}
</style>
<script id="kitchen-audio-visual-fix-script">
(function(){
 function soften(){const b=document.getElementById('phase33-audio');if(!b)return;if(!b.classList.contains('ready'))b.setAttribute('title','Le son s’active au premier toucher de l’écran Cuisine');}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',soften);else soften();setTimeout(soften,300);
})();
</script>
'''
        if "kitchen-audio-visual-fix" not in html:
            html = html.replace("</body>", addon + "</body>")
            response.set_data(html)
            response.content_length = len(response.get_data())
        return response

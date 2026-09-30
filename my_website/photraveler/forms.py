from django import forms
from django.utils.translation import gettext_lazy as _

from .models import MapPin


class PinForm(forms.ModelForm):
    """ピンの追加・編集。写真は views 側で photos.process_photo() を通して扱う。"""
    latitude = forms.FloatField(required=False, min_value=-90, max_value=90)
    longitude = forms.FloatField(required=False, min_value=-180, max_value=180)

    class Meta:
        model = MapPin
        # 緯度・経度はモデルの Decimal 検証 (小数 6 桁) にかけず、views 側で丸めてから設定する
        fields = ('title', 'description', 'place_name', 'country', 'visited_on')
        widgets = {'visited_on': forms.DateInput(attrs={'type': 'date'})}

    def clean_description(self):
        description = self.cleaned_data.get('description', '')
        if len(description) > 2000:
            raise forms.ValidationError(_('説明は 2000 文字以内で入力してください。'))
        return description

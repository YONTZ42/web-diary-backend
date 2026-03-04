from rembg import remove, new_session
from PIL import Image
import io

# IS-Net モデルを指定
session = new_session("birefnet-general-lite")

# 画像の読み込み
input_path = 'input.jpg' # あなたの写真
output_path = 'output.png'

with open(input_path, 'rb') as i:
    input_data = i.read()
    # 推論実行
    output_data = remove(input_data, session=session,
    )
    
    with open(output_path, 'wb') as o:
        o.write(output_data)

print("IS-Netによる切り抜きが完了しました！")
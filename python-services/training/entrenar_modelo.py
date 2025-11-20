"""
🎓 ENTRENAR MODELO YOLO PERSONALIZADO
Entrena un modelo YOLO con tu dataset capturado
"""
import os
import shutil
import yaml
from datetime import datetime


def preparar_dataset_yolo(dataset_path, output_path):
    """
    Convierte dataset capturado a formato YOLO
    """
    print("=" * 70)
    print("  📦 PREPARANDO DATASET PARA YOLO")
    print("=" * 70 + "\n")
    
    # Crear estructura YOLO
    yolo_path = output_path
    train_images = os.path.join(yolo_path, "images", "train")
    val_images = os.path.join(yolo_path, "images", "val")
    train_labels = os.path.join(yolo_path, "labels", "train")
    val_labels = os.path.join(yolo_path, "labels", "val")
    
    for path in [train_images, val_images, train_labels, val_labels]:
        os.makedirs(path, exist_ok=True)
    
    # Categorías
    categorias = ['excavacion', 'construccion', 'peligro', 'zona_libre', 
                  'objetivo', 'obstaculo', 'otro']
    
    # Contar imágenes
    total_imagenes = 0
    imagenes_por_categoria = {}
    
    for idx, categoria in enumerate(categorias):
        cat_path = os.path.join(dataset_path, categoria)
        if not os.path.exists(cat_path):
            print(f"⚠️  Categoría '{categoria}' no encontrada, creando...")
            os.makedirs(cat_path, exist_ok=True)
            imagenes_por_categoria[categoria] = 0
            continue
        
        imagenes = [f for f in os.listdir(cat_path) if f.endswith(('.jpg', '.png'))]
        imagenes_por_categoria[categoria] = len(imagenes)
        total_imagenes += len(imagenes)
        
        # Split 80% train, 20% val
        split_idx = int(len(imagenes) * 0.8)
        
        for i, img_name in enumerate(imagenes):
            img_path = os.path.join(cat_path, img_name)
            
            # Determinar si va a train o val
            if i < split_idx:
                dest_images = train_images
                dest_labels = train_labels
            else:
                dest_images = val_images
                dest_labels = val_labels
            
            # Copiar imagen
            new_img_name = f"{categoria}_{i:04d}.jpg"
            shutil.copy(img_path, os.path.join(dest_images, new_img_name))
            
            # Crear label (toda la imagen es de esta clase)
            # Formato YOLO: class_id x_center y_center width height (normalized)
            label_name = new_img_name.replace('.jpg', '.txt').replace('.png', '.txt')
            label_path = os.path.join(dest_labels, label_name)
            
            with open(label_path, 'w') as f:
                # Clase completa de la imagen (toda la imagen)
                f.write(f"{idx} 0.5 0.5 1.0 1.0\n")
    
    print(f"✅ Dataset preparado:")
    print(f"   📁 {total_imagenes} imágenes totales")
    print(f"   📁 {int(total_imagenes * 0.8)} para entrenamiento")
    print(f"   📁 {int(total_imagenes * 0.2)} para validación\n")
    
    print("📊 Imágenes por categoría:")
    for cat, count in imagenes_por_categoria.items():
        print(f"   {cat:15} : {count:4} imágenes")
    
    # Crear archivo data.yaml
    data_yaml = {
        'path': os.path.abspath(yolo_path),
        'train': 'images/train',
        'val': 'images/val',
        'nc': len(categorias),
        'names': categorias
    }
    
    yaml_path = os.path.join(yolo_path, 'data.yaml')
    with open(yaml_path, 'w') as f:
        yaml.dump(data_yaml, f, default_flow_style=False)
    
    print(f"\n✅ Archivo data.yaml creado: {yaml_path}\n")
    
    return yaml_path, total_imagenes


def entrenar_modelo(data_yaml, epochs=50, imgsz=320):
    """
    Entrena modelo YOLO personalizado
    """
    print("=" * 70)
    print("  🚀 ENTRENANDO MODELO YOLO")
    print("=" * 70 + "\n")
    
    try:
        from ultralytics import YOLO
        
        # Cargar modelo base
        print("📥 Cargando modelo base YOLOv11n...")
        model = YOLO('yolo11n.pt')
        
        print(f"🎯 Configuración:")
        print(f"   Epochs: {epochs}")
        print(f"   Tamaño de imagen: {imgsz}x{imgsz}")
        print(f"   Dataset: {data_yaml}\n")
        
        print("⏳ Entrenando... (esto puede tardar 5-30 minutos)\n")
        
        # Entrenar
        results = model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=8,
            name='rover_custom',
            patience=10,
            save=True,
            plots=True,
            verbose=True
        )
        
        print("\n" + "=" * 70)
        print("  ✅ ENTRENAMIENTO COMPLETADO")
        print("=" * 70 + "\n")
        
        # Ubicación del modelo
        model_path = os.path.join('runs', 'detect', 'rover_custom', 'weights', 'best.pt')
        
        if os.path.exists(model_path):
            # Copiar a raíz del proyecto
            dest_path = 'modelo_rover_custom.pt'
            shutil.copy(model_path, dest_path)
            print(f"✅ Modelo guardado en: {os.path.abspath(dest_path)}")
            print(f"📁 Resultados de entrenamiento: runs/detect/rover_custom/")
            
            return dest_path
        else:
            print(f"⚠️  No se encontró el modelo en {model_path}")
            return None
    
    except ImportError:
        print("❌ Error: ultralytics no está instalado")
        print("   Instalar con: pip install ultralytics")
        return None
    except Exception as e:
        print(f"❌ Error durante el entrenamiento: {e}")
        return None


def main():
    """Función principal"""
    print("\n" + "=" * 70)
    print("  🎓 ENTRENADOR DE MODELO YOLO PERSONALIZADO")
    print("=" * 70 + "\n")
    
    # Rutas
    base_path = os.path.dirname(__file__)
    dataset_path = os.path.join(base_path, "..", "..", "dataset_rover")
    yolo_path = os.path.join(base_path, "..", "..", "dataset_yolo")
    
    # Verificar que existe el dataset
    if not os.path.exists(dataset_path):
        print(f"❌ Dataset no encontrado: {dataset_path}")
        print("   Primero captura imágenes con capturar_dataset.py")
        return
    
    # Contar imágenes totales
    total = 0
    for categoria in ['excavacion', 'construccion', 'peligro', 'zona_libre', 
                      'objetivo', 'obstaculo', 'otro']:
        cat_path = os.path.join(dataset_path, categoria)
        if os.path.exists(cat_path):
            imagenes = [f for f in os.listdir(cat_path) if f.endswith(('.jpg', '.png'))]
            total += len(imagenes)
    
    print(f"📦 Dataset encontrado: {total} imágenes")
    
    if total < 10:
        print("⚠️  Tienes muy pocas imágenes!")
        print("   Se recomienda al menos 50 imágenes por categoría")
        respuesta = input("\n¿Continuar de todas formas? (s/n): ")
        if respuesta.lower() != 's':
            print("❌ Entrenamiento cancelado")
            return
    
    # Configuración
    print("\n⚙️  CONFIGURACIÓN:")
    
    try:
        epochs_input = input("   Epochs [50]: ").strip()
        epochs = int(epochs_input) if epochs_input else 50
    except ValueError:
        epochs = 50
    
    try:
        imgsz_input = input("   Tamaño de imagen [320]: ").strip()
        imgsz = int(imgsz_input) if imgsz_input else 320
    except ValueError:
        imgsz = 320
    
    print(f"\n✅ Configuración final:")
    print(f"   📊 Imágenes: {total}")
    print(f"   🔄 Epochs: {epochs}")
    print(f"   📐 Tamaño: {imgsz}x{imgsz}")
    
    input("\nPresiona ENTER para comenzar el entrenamiento...")
    
    # Preparar dataset
    data_yaml, num_imgs = preparar_dataset_yolo(dataset_path, yolo_path)
    
    if num_imgs == 0:
        print("\n❌ No hay imágenes para entrenar")
        return
    
    # Entrenar
    model_path = entrenar_modelo(data_yaml, epochs=epochs, imgsz=imgsz)
    
    if model_path:
        print("\n" + "=" * 70)
        print("  🎉 ¡LISTO PARA USAR!")
        print("=" * 70)
        print(f"\n📝 Para usar tu modelo personalizado:")
        print(f"\n1. Edita: python-services/camera/camera_client.py")
        print(f"2. Cambia la línea 32:")
        print(f"   self.model = YOLO('yolo11n.pt')")
        print(f"   Por:")
        print(f"   self.model = YOLO('modelo_rover_custom.pt')")
        print(f"\n3. Reinicia el sistema con: iniciar_rover.bat")
        print("\n" + "=" * 70 + "\n")
    else:
        print("\n❌ Entrenamiento fallido")


if __name__ == "__main__":
    main()

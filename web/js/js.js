const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth/window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

// Luz
const light = new THREE.DirectionalLight(0xffffff, 1);
light.position.set(1, 1, 1).normalize();
scene.add(light);

// Cargar STL
const loader = new THREE.STLLoader();
loader.load('Wheel.stl', function (geometry) {
  const material = new THREE.MeshPhongMaterial({ color: 0x555555 });
  const mesh = new THREE.Mesh(geometry, material);
  scene.add(mesh);
});

camera.position.z = 100;

function animate() {
  requestAnimationFrame(animate);
  renderer.render(scene, camera);
}
animate();
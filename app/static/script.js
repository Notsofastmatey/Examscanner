const imageInput = document.getElementById("imageInput");
const imageTag = document.getElementById("adpImage");
const getCropped = document.getElementById("getCropped");
const croppedImg = document.getElementById("croppedImage");
const dataUrl = document.getElementById("dataUrl");
imageInput.addEventListener("change", e => {
  var reader = new FileReader();
  reader.readAsDataURL(e.target.files[0]);
  reader.onload = () => {
    imageTag.src = reader.result;
    initCropper();
  };
});
function initCropper() {
  const cropper = new Cropper(imageTag);
  getCropped.addEventListener("click", () => {
    let croppedImgCanvas = cropper.getCroppedCanvas({
      width: 160,
      height: 90,
      minWidth: 256,
      minHeight: 256,
      maxWidth: 4096,
      maxHeight: 4096,
      fillColor: "#fff",
      imageSmoothingEnabled: false,
      imageSmoothingQuality: "high"
    });
    croppedImg.appendChild(croppedImgCanvas);
    imageParams = cropper.getData();
    dataUrl.value = JSON.stringify(imageParams);
    console.log(imageParams);
  });
}

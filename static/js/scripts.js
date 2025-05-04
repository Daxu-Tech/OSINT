document.addEventListener("DOMContentLoaded", function () {
    const dynamicColors = ["#222", "#333", "#444", "#555", "#666", "#777", "#888"];
    
    const carouselElement = document.getElementById('carouselExampleControls');
    const carousel = new bootstrap.Carousel(carouselElement, {
      interval: 5000,
      ride: "carousel"
    });
    
    function updateCarouselBackground() {
      const activeItem = carouselElement.querySelector('.carousel-item.active');
      const items = Array.from(carouselElement.querySelectorAll('.carousel-item'));
      const activeIndex = items.indexOf(activeItem);
      const newColor = dynamicColors[activeIndex % dynamicColors.length];
      document.getElementById('carouselContainer').style.backgroundColor = newColor;
    }
    
    carouselElement.addEventListener('slid.bs.carousel', function () {
      updateCarouselBackground();
    });
    updateCarouselBackground();
    
    document.getElementById('carouselPrev').addEventListener('click', function () {
      carousel.prev();
      carousel.pause();
      carousel.cycle();
    });
    
    document.getElementById('carouselNext').addEventListener('click', function () {
      carousel.next();
      carousel.pause();
      carousel.cycle();
    });
  });
  
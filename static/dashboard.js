document.addEventListener("DOMContentLoaded", function() {
  const toggleElements = document.querySelectorAll(".toggle-btn");
  toggleElements.forEach(function(el) {
      el.addEventListener("click", function() {
          const idx = el.getAttribute("data-index");
          const detailsRow = document.getElementById("details-" + idx);
          if (detailsRow.style.display === "none" || detailsRow.style.display === "") {
              detailsRow.style.display = "table-row";
          } else {
              detailsRow.style.display = "none";
          }
      });
  });
});

const express = require('express');
const PDFDocument = require('pdfkit');
const fs = require('fs');
const path = require('path');
const unixPrint = require('unix-print');

const app = express();
app.use(express.json());

const PORT = 3000;
const REFUND_RATE = 0.10; // 10 cents per container

// unixPrint.getPrinters().then((printers) => {
//     console.log(printers);
// });

app.post('/print-receipt', async (req, res) => {
    try {
        const { totalCount, categories } = req.body;
        const refundTotal = (totalCount * REFUND_RATE).toFixed(2);
        
        // Create a new PDF document
        const doc = new PDFDocument();
        const filePath = path.join(__dirname, 'temp-receipt.pdf');
        const writeStream = fs.createWriteStream(filePath);
        
        // Pipe PDF to writeStream
        doc.pipe(writeStream);
        
        // Add company logo (using a placeholder rectangle for this example)
        doc.rect(50, 50, 100, 50)
           .stroke()
           .fontSize(16)
           .text('ECO RECYCLING', 65, 65);
        
        // Add receipt content
        doc.moveDown()
           .fontSize(14)
           .text('Container Return Receipt', { underline: true })
           .moveDown();
        
        // Add container categories
        doc.fontSize(12);
        for (const [category, count] of Object.entries(categories)) {
            doc.text(`${category}: ${count} containers`);
        }
        
        doc.moveDown()
           .text(`Total Containers: ${totalCount}`)
           .text(`Refund Rate: $${REFUND_RATE.toFixed(2)} per container`)
           .moveDown()
           .fontSize(14)
           .text(`Total Refund: $${refundTotal}`, { bold: true })
           .moveDown(2)
           .fontSize(10)
           .text(`Date: ${new Date().toLocaleString()}`)
           .text('Thank you for recycling!');
        
        // Finalize PDF
        doc.end();
        
        // Wait for PDF to finish writing
        writeStream.on('finish', async () => {
            try {
                // Print the PDF
                await unixPrint.print(filePath, '80Series2');
                
                // Clean up temporary file
                fs.unlinkSync(filePath);
                
                res.json({
                    success: true,
                    message: 'Receipt printed successfully',
                    refundTotal
                });
            } catch (printError) {
                res.status(500).json({
                    success: false,
                    message: 'Error printing receipt',
                    error: printError.message
                });
            }
        });
        
    } catch (error) {
        res.status(500).json({
            success: false,
            message: 'Error generating receipt',
            error: error.message
        });
    }
});

app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});